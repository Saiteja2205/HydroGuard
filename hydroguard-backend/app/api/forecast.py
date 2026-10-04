"""Forecast API endpoint for HydroGuard water quality forecasting."""

from datetime import datetime, timedelta, timezone
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_student_or_admin
from app.db.repositories import EnsembleWeightRepository, ForecastRepository, ModelErrorRepository, NodeRepository
from app.schemas.forecasts import ForecastListResponse, ForecastRecord, ModelPerformance, ModelPerformanceResponse
from app.schemas.readings import ForecastRequest, ForecastResponse
from ml.services import create_forecast_service, ForecastServiceConfig

router = APIRouter(tags=["forecast"])

# Global forecast service instance
forecast_service = None


def get_forecast_service() -> "ForecastService":
    """Get or create the forecast service instance."""
    global forecast_service
    if forecast_service is None:
        config = ForecastServiceConfig(
            four_parameter_mode=True,
            parameters=("pH", "TDS", "turbidity", "temperature"),
            ensemble_window_size=30,
            ensemble_alpha=0.5,
            device="cpu",  # Force CPU to avoid device issues
        )
        forecast_service = create_forecast_service(config)
    return forecast_service


@router.post("/forecast", response_model=ForecastResponse)
def generate_forecast(
    request: ForecastRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_student_or_admin),
) -> ForecastResponse:
    """Generate a forecast only from real, timestamped request observations."""
    try:
        min_history = int(os.getenv("HYDROGUARD_FORECAST_MIN_HISTORY", "30"))
        if len(request.readings) < min_history:
            raise HTTPException(status_code=422, detail=f"Insufficient historical data for reliable forecasting. At least {min_history} valid timestamped observations are required.")
        sources = {reading.source for reading in request.readings}
        if len(sources) != 1:
            raise HTTPException(status_code=422, detail="Forecast history cannot mix data provenance sources.")
        if NodeRepository.get_by_node_id(db, request.node_id) is None:
            raise HTTPException(status_code=404, detail=f"Node {request.node_id} not found")

        service = get_forecast_service()
        expected_parameters = ("pH", "TDS", "turbidity", "temperature")
        if tuple(service.config.parameters) != expected_parameters:
            raise HTTPException(status_code=503, detail="Loaded model checkpoints do not match the active four-parameter model contract.")

        # Load models if not already loaded
        if not service.models_loaded:
            try:
                service.load_models()
            except FileNotFoundError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Forecast model checkpoint not found: {str(e)}",
                )

        # Convert readings to numpy array
        import numpy as np

        selected_readings = request.readings[-service.config.window_size:]
        readings_array = [[r.pH, r.TDS, r.turbidity, r.temperature] for r in selected_readings]

        input_window = np.array(readings_array, dtype=np.float32)

        # Validate input shape and NaN values
        service.validate_input_shape(input_window)

        # Restore persisted adaptive weights where every model has comparable,
        # parameter-specific observations. Otherwise use the documented fallback.
        from ml.ensemble.weighting import calculate_parameter_weights
        model_names = ("LSTM", "PatchTST", "TimeMixer")
        parameters = expected_parameters
        data_source = next(iter(sources))
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
                    EnsembleWeightRepository.set_weight(db, request.node_id, parameter, model_name, weight, 1, data_source=data_source)
        if not adaptive:
            weights = {p: {model: 1.0 / len(model_names) for model in model_names} for p in parameters}
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
            },
            model_predictions=formatted_model_predictions,
            weights=formatted_weights,
            node_id=request.node_id,
            input_start=input_start.isoformat(),
            input_end=input_end.isoformat(),
            data_source=data_source,
            model_versions=forecast_result["model_versions"],
            weight_strategy="adaptive" if adaptive else "initial",
            weight_status="Adaptive weights from persisted model errors." if adaptive else "Initial weights — insufficient historical model performance data.",
            optical_colour_forecast_available=False,
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

    return ModelPerformanceResponse(node_id=node_id, performance=performance_list)
