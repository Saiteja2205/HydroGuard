"""Forecast API endpoint for HydroGuard water quality forecasting."""

from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path as FilePath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_student_or_admin
from app.db.models import SensorReading
from app.db.repositories import EnsembleWeightRepository, ForecastRepository, ModelErrorRepository, NodeRepository
from app.schemas.forecasts import ForecastListResponse, ForecastRecord, ModelPerformance, ModelPerformanceResponse
from app.schemas.readings import ForecastReading, ForecastRequest, ForecastResponse
from ml.services import create_forecast_service, ForecastServiceConfig

router = APIRouter(tags=["forecast"])

# Global forecast service instance
forecast_service = None


def _development_evaluation() -> dict | None:
    """Read only the checked-in, provenance-validated development evaluation."""
    if os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower() not in {"development", "dev", "test"}:
        return None
    backend_root = FilePath(__file__).resolve().parents[2]
    evaluation_path = backend_root / "artifacts" / "results" / "five_parameter_evaluation.json"
    try:
        with evaluation_path.open(encoding="utf-8") as evaluation_file:
            evaluation = json.load(evaluation_file)
    except (OSError, json.JSONDecodeError):
        return None
    if (
        evaluation.get("dataset_size") != 200
        or evaluation.get("dataset_source") != "SIMULATED_DEVELOPMENT"
        or evaluation.get("split") != {"train": 140, "validation": 30, "test": 30}
        or evaluation.get("window_size") != 30
        or evaluation.get("parameters") != ["pH", "TDS", "turbidity", "temperature", "optical_colour_index"]
    ):
        return None
    return evaluation


def _validated_development_weights(evaluation: dict | None) -> dict[str, dict[str, float]] | None:
    if evaluation is None:
        return None
    model_names = ("LSTM", "PatchTST", "TimeMixer")
    weights = evaluation.get("adaptive_ensemble_weights_from_validation")
    normalized: dict[str, dict[str, float]] = {}
    for parameter in ("pH", "TDS", "turbidity", "temperature", "optical_colour_index"):
        values = (weights or {}).get(parameter)
        if not isinstance(values, dict) or set(values) != set(model_names):
            return None
        numeric = {model: float(values[model]) for model in model_names}
        if any(not math.isfinite(value) or value < 0 for value in numeric.values()):
            return None
        total = sum(numeric.values())
        if total <= 0:
            return None
        normalized[parameter] = {model: value / total for model, value in numeric.items()}
    return normalized


def get_forecast_service() -> "ForecastService":
    """Get or create the forecast service instance."""
    global forecast_service
    if forecast_service is None:
        config = ForecastServiceConfig(
            five_parameter_mode=True,
            parameters=("pH", "TDS", "turbidity", "temperature", "optical_colour_index"),
            ensemble_window_size=30,
            ensemble_alpha=0.5,
            device="cpu",  # Force CPU to avoid device issues
        )
        forecast_service = create_forecast_service(config)
    return forecast_service


def _forecast_history(request: ForecastRequest, db: Session) -> tuple[list[ForecastReading], str]:
    """Resolve history while keeping simulated provenance out of production."""
    environment = os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower()
    development_mode = environment in {"development", "dev"}

    if request.readings is None:
        if not development_mode:
            raise HTTPException(
                status_code=422,
                detail="Timestamped REAL_SENSOR request observations are required outside development mode.",
            )
        source = request.source or "SIMULATED_DEVELOPMENT"
        if source != "SIMULATED_DEVELOPMENT":
            raise HTTPException(
                status_code=422,
                detail="Stored-data forecasting in development mode requires source SIMULATED_DEVELOPMENT.",
            )

        rows = (
            db.query(SensorReading)
            .filter(
                SensorReading.node_id == request.node_id,
                SensorReading.source == "SIMULATED_DEVELOPMENT",
            )
            .order_by(SensorReading.timestamp.asc(), SensorReading.id.asc())
            .all()
        )
        readings: list[ForecastReading] = []
        for row in rows:
            timestamp = row.timestamp
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            readings.append(ForecastReading(
                timestamp=timestamp.astimezone(timezone.utc).isoformat(),
                pH=float(row.ph),
                TDS=float(row.tds),
                turbidity=float(row.turbidity),
                temperature=float(row.temperature),
                red=row.red,
                green=row.green,
                blue=row.blue,
                clear=row.clear,
                optical_colour_index=row.optical_colour_index,
                calibration_id=row.calibration_id,
                source=row.source,
            ))
        return readings, source

    sources = {reading.source for reading in request.readings}
    if len(sources) != 1:
        raise HTTPException(status_code=422, detail="Forecast history cannot mix data provenance sources.")
    source = next(iter(sources))
    if request.source is not None and request.source != source:
        raise HTTPException(status_code=422, detail="Request source must match every forecast observation.")
    if not development_mode and source != "REAL_SENSOR":
        raise HTTPException(
            status_code=422,
            detail="Production forecasts require timestamped REAL_SENSOR observations.",
        )
    return request.readings, source


@router.post("/forecast", response_model=ForecastResponse)
def generate_forecast(
    request: ForecastRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_student_or_admin),
) -> ForecastResponse:
    """Forecast real request observations, or stored simulated history in development only."""
    try:
        min_history = int(os.getenv("HYDROGUARD_FORECAST_MIN_HISTORY", "30"))
        if request.readings is not None and len(request.readings) < min_history:
            raise HTTPException(status_code=422, detail=f"Insufficient historical data for reliable forecasting. At least {min_history} valid timestamped observations are required.")
        if NodeRepository.get_by_node_id(db, request.node_id) is None:
            raise HTTPException(status_code=404, detail=f"Node {request.node_id} not found")

        readings, data_source = _forecast_history(request, db)
        if len(readings) < min_history:
            raise HTTPException(status_code=422, detail=f"Insufficient historical data for reliable forecasting. At least {min_history} valid timestamped observations are required.")

        service = get_forecast_service()
        expected_parameters = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")
        if tuple(service.config.parameters) != expected_parameters:
            raise HTTPException(status_code=503, detail="Loaded model checkpoints do not match the active five-parameter model contract.")

        # Load models if not already loaded
        if not service.models_loaded:
            try:
                service.load_models()
            except FileNotFoundError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Forecast model checkpoint not found: {str(e)}",
                )
            except ValueError as e:
                raise HTTPException(status_code=503, detail=f"Forecast model checkpoint is incompatible: {e}")

        # Convert readings to numpy array
        import numpy as np

        selected_readings = readings[-service.config.window_size:]
        readings_array = [[r.pH, r.TDS, r.turbidity, r.temperature, r.optical_colour_index] for r in selected_readings]

        input_window = np.array(readings_array, dtype=np.float32)

        # Validate input shape and NaN values
        service.validate_input_shape(input_window)

        # Restore persisted adaptive weights where every model has comparable,
        # parameter-specific observations. Otherwise use the documented fallback.
        from ml.ensemble.weighting import calculate_parameter_weights
        model_names = ("LSTM", "PatchTST", "TimeMixer")
        parameters = expected_parameters
        persisted = EnsembleWeightRepository.get_by_node(db, request.node_id, data_source=data_source)
        persisted_weights = {
            parameter: {row.model_name: float(row.weight) for row in persisted if row.parameter == parameter}
            for parameter in parameters
        }
        adaptive = all(set(persisted_weights[parameter]) == set(model_names) for parameter in parameters)
        weights = persisted_weights if adaptive else {}
        recent_errors = {}
        if not adaptive:
            for parameter in parameters:
                recent_errors[parameter] = {}
                for model_name in model_names:
                    rows = ModelErrorRepository.get_recent_errors(db, request.node_id, model_name, parameter, window_size=30, data_source=data_source)
                    if rows:
                        mae = sum(float(row.absolute_error) for row in rows) / len(rows)
                        rmse = (sum(float(row.squared_error) for row in rows) / len(rows)) ** 0.5
                        recent_errors[parameter][model_name] = 0.5 * mae + 0.5 * rmse
            adaptive = all(set(recent_errors[p]) == set(model_names) for p in parameters)
        if adaptive and not weights:
            errors_by_model = {m: {p: recent_errors[p][m] for p in parameters} for m in model_names}
            weights = calculate_parameter_weights(errors_by_model)
            for parameter, model_weights in weights.items():
                for model_name, weight in model_weights.items():
                    EnsembleWeightRepository.set_weight(
                        db, request.node_id, parameter, model_name, weight, 1,
                        data_source=data_source, model_version=service._checkpoint_version(
                            getattr(service.config, f"{model_name.lower()}_checkpoint_path")
                        ),
                    )
        initial_weight_status = ""
        if not adaptive:
            development_weights = (
                _validated_development_weights(_development_evaluation())
                if data_source == "SIMULATED_DEVELOPMENT"
                else None
            )
            if development_weights is not None:
                weights = development_weights
                initial_weight_status = (
                    "Parameter-specific starting weights from the 30-observation validation split "
                    "of the 200-observation SIMULATED_DEVELOPMENT dataset."
                )
            else:
                weights = {p: {model: 1.0 / len(model_names) for model in model_names} for p in parameters}
                initial_weight_status = "Initial equal weights — insufficient historical model performance data."
        if service.ensemble is not None:
            service.ensemble.state.current_weights = weights

        forecast_result = service.generate_forecast(input_window)

        # Convert to response format
        prediction = forecast_result["prediction"]
        model_predictions = forecast_result["model_predictions"]
        weights = weights if adaptive else forecast_result["weights"]
        if service.ensemble is not None:
            prediction = service.ensemble.combine(model_predictions)

        # Format model predictions
        formatted_model_predictions = {}
        for model_name, preds in model_predictions.items():
            formatted_model_predictions[model_name] = {
                "pH": preds["pH"],
                "TDS": preds["TDS"],
                "turbidity": preds["turbidity"],
                "temperature": preds["temperature"],
                "optical_colour_index": preds["optical_colour_index"],
            }

        # Format weights
        formatted_weights = {}
        for param, param_weights in weights.items():
            formatted_weights[param] = {
                "LSTM": param_weights["LSTM"],
                "PatchTST": param_weights["PatchTST"],
                "TimeMixer": param_weights["TimeMixer"],
            }

        input_start = datetime.fromisoformat(selected_readings[0].timestamp.replace("Z", "+00:00"))
        input_end = datetime.fromisoformat(selected_readings[-1].timestamp.replace("Z", "+00:00"))
        forecast_date = input_end + timedelta(days=1)

        # Store forecast
        try:
            ForecastRepository.create(
                db=db,
                node_id=request.node_id,
                forecast_date=forecast_date,
                lstm_predictions=model_predictions.get("LSTM", {}),
                patchtst_predictions=model_predictions.get("PatchTST", {}),
                timemixer_predictions=model_predictions.get("TimeMixer", {}),
                ensemble_predictions=prediction,
                weights=weights,
                input_start=input_start,
                input_end=input_end,
                data_source=data_source,
                model_versions=forecast_result["model_versions"],
                weight_strategy="adaptive" if adaptive else "initial",
                horizon_hours=24,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Forecast persistence failed: {e}")

        response = ForecastResponse(
            forecast_date=forecast_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            prediction={
                "pH": prediction["pH"],
                "TDS": prediction["TDS"],
                "turbidity": prediction["turbidity"],
                "temperature": prediction["temperature"],
                "optical_colour_index": prediction["optical_colour_index"],
            },
            model_predictions=formatted_model_predictions,
            weights=formatted_weights,
            node_id=request.node_id,
            input_start=input_start.isoformat(),
            input_end=input_end.isoformat(),
            data_source=data_source,
            model_versions=forecast_result["model_versions"],
            weight_strategy="adaptive" if adaptive else "initial",
            weight_status="Adaptive weights from persisted model errors." if adaptive else initial_weight_status,
            forecast_horizon_hours=24,
        )

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast generation failed: {str(e)}")


@router.get("/nodes/{node_id}/forecasts", response_model=ForecastListResponse)
def get_forecasts(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum number of forecasts"),
    db: Session = Depends(get_db),
) -> ForecastListResponse:
    """Get stored forecasts for a node."""
    # Ensure node exists
    node = NodeRepository.get_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    forecasts = ForecastRepository.get_by_node(db, node_id, limit=limit)
    return ForecastListResponse(forecasts=forecasts, count=len(forecasts))


@router.get("/nodes/{node_id}/model-performance", response_model=ModelPerformanceResponse)
def get_model_performance(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    db: Session = Depends(get_db),
) -> ModelPerformanceResponse:
    """Get model performance metrics for a node."""
    # Ensure node exists
    node = NodeRepository.get_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    from app.db.repositories import ModelErrorRepository

    # Keep data provenance groups separate; synthetic/demo errors must never
    # be blended into field-data metrics.
    rows = ModelErrorRepository.get_recent_errors(db, node_id, window_size=10000)
    groups = {}
    for row in rows:
        key = (row.data_source, row.model_name, row.parameter, row.horizon_hours)
        groups.setdefault(key, []).append(row)
    performance_list = []
    for (source, model_name, parameter, horizon_hours), samples in groups.items():
        # Report a fixed rolling window so changes in recent model behavior are
        # visible and evaluation periods remain explicit.
        samples = samples[:30]
        mae = sum(float(item.absolute_error) for item in samples) / len(samples)
        rmse = (sum(float(item.squared_error) for item in samples) / len(samples)) ** 0.5
        mape_samples = [item for item in samples if abs(float(item.actual_value)) >= 1e-9]
        mape = (
            sum(float(item.absolute_error) / abs(float(item.actual_value)) * 100 for item in mape_samples) / len(mape_samples)
            if mape_samples else None
        )
        evaluation_times = [item.evaluated_at for item in samples if item.evaluated_at is not None]
        performance_list.append(ModelPerformance(
            model_name=model_name,
            parameter=parameter,
            mae=mae,
            rmse=rmse,
            count=len(samples),
            data_source=source,
            mape=mape,
            horizon_hours=horizon_hours,
            evaluation_start=min(evaluation_times) if evaluation_times else None,
            evaluation_end=max(evaluation_times) if evaluation_times else None,
        ))

    evaluation = _development_evaluation()
    if evaluation is not None:
        existing = {
            (item.data_source, item.model_name, item.parameter, item.horizon_hours)
            for item in performance_list
        }
        test_count = int(evaluation["split"]["test"])
        metric_groups = [
            *evaluation.get("test_metrics_by_model", {}).items(),
            ("Adaptive Ensemble", evaluation.get("adaptive_ensemble_test_metrics", {})),
        ]
        for model_name, parameter_metrics in metric_groups:
            for parameter in evaluation["parameters"]:
                key = ("SIMULATED_DEVELOPMENT", model_name, parameter, 24)
                if key in existing:
                    continue
                metrics = parameter_metrics.get(parameter)
                if not isinstance(metrics, dict):
                    continue
                mae = float(metrics.get("MAE", math.nan))
                rmse = float(metrics.get("RMSE", math.nan))
                mape_value = metrics.get("MAPE")
                mape = float(mape_value) if mape_value is not None else None
                if not math.isfinite(mae) or not math.isfinite(rmse) or (mape is not None and not math.isfinite(mape)):
                    continue
                performance_list.append(ModelPerformance(
                    model_name=model_name,
                    parameter=parameter,
                    mae=mae,
                    rmse=rmse,
                    count=test_count,
                    data_source="SIMULATED_DEVELOPMENT",
                    mape=mape,
                    horizon_hours=24,
                ))

    return ModelPerformanceResponse(node_id=node_id, performance=performance_list)
