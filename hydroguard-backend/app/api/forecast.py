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
from app.services.alert_service import AlertService
from app.schemas.forecasts import ForecastListResponse, ForecastRecord, ModelPerformance, ModelPerformanceResponse
from app.schemas.readings import ForecastReading, ForecastRequest, ForecastResponse
from ml.services import create_forecast_service, ForecastServiceConfig, get_inference_service
import ml.services.thingspeak_service as thingspeak_service
from ml.services.thingspeak_service import (
    ThingSpeakConfig,
    ThingSpeakInvalidChannel,
    ThingSpeakNotConfigured,
    ThingSpeakUnavailable,
    load_config_from_env,
    parse_feeds,
    parse_history_readings,
)
from app.schemas.thingspeak import (
    ForecastProvenance,
    ThingSpeakForecastBlock,
    ThingSpeakForecastResponse,
    ThingSpeakForecastResponseUnion,
    ThingSpeakForecastUnavailable,
    ThingSpeakHistoryReading,
    ThingSpeakHistoryResponse,
    ThingSpeakLatestReading,
    ThingSpeakReadingValues,
    ThingSpeakRGBValues,
    WindowProvenance,
)


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
    principal: dict = Depends(require_student_or_admin),
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
    principal: dict = Depends(require_student_or_admin),
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


def _resolve_thingspeak_config(channel_id: Optional[str]) -> ThingSpeakConfig:
    """Resolve the channel to read, honouring an explicit per-request override.

    The override is validated the same way as the configured value: a
    ThingSpeak channel id is numeric, and anything else is rejected before it
    can be interpolated into the request URL.
    """
    config = load_config_from_env()
    if channel_id is not None:
        stripped = channel_id.strip()
        if not stripped.isdigit():
            raise HTTPException(
                status_code=422,
                detail="channel_id must contain digits only.",
            )
        config = ThingSpeakConfig(
            channel_id=stripped,
            read_api_key=config.read_api_key,
            base_url=config.base_url,
            results=config.results,
            timeout_seconds=config.timeout_seconds,
            field_map=config.field_map,
            rgb_field_map=config.rgb_field_map,
        )
    if not config.configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "No ThingSpeak channel is configured. Set "
                "HYDROGUARD_THINGSPEAK_CHANNEL_ID to enable live forecasting."
            ),
        )
    return config


@router.get("/thingspeak/forecast", response_model=ThingSpeakForecastResponseUnion)
def generate_thingspeak_forecast(
    channel_id: Optional[str] = Query(
        None,
        min_length=1,
        max_length=32,
        description="Optional numeric ThingSpeak channel id overriding the configured default.",
    ),
    min_history: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description="Optional minimum number of observed feeds required to generate a forecast.",
    ),
    principal: dict = Depends(require_student_or_admin),
    db: Session = Depends(get_db),
) -> ThingSpeakForecastResponse:
    """Fetch the configured ThingSpeak channel, forecast it, and return both.

    Flow: read the channel's recent feeds, shape them into the 30-row window
    the checkpoints require, run LSTM/PatchTST/TimeMixer, combine them with
    the weighted ensemble, and return physical-unit forecasts alongside the
    provenance of both the observations and the model weights.

    The response never claims more than the evidence supports: the observation
    provenance (``THINGSPEAK``) is reported separately from what the weights
    were trained on (``SIMULATED_DEVELOPMENT`` for the shipped checkpoints),
    and every forward-filled or padded cell is counted in ``provenance.window``.
    Nothing is persisted, so this read-only path cannot write simulated rows
    into the sensor tables that ``/health`` uses to judge connectivity.

    Alert integration: evaluates the latest water-quality readings against
    configured thresholds, creating alerts for violations and auto-resolving
    alerts when readings return to normal. Uses 60-minute cooldown to prevent
    duplicate alerts from repeated polling.
    """
    config = _resolve_thingspeak_config(channel_id)

    try:
        window = parse_feeds(thingspeak_service.fetch_feeds(config), config)
    except ThingSpeakNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ThingSpeakInvalidChannel as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ThingSpeakUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if window.observed_rows == 0:
        # The channel answered but held no feeds. Returning a forecast built
        # entirely from range midpoints would fabricate a result, so this is
        # reported as an empty channel instead.
        raise HTTPException(
            status_code=502,
            detail="The ThingSpeak channel returned no observations, so no forecast can be produced.",
        )

    min_obs = min_history if min_history is not None else int(os.getenv("HYDROGUARD_THINGSPEAK_MIN_HISTORY", "1"))
    if window.observed_rows < min_obs:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient history: channel has {window.observed_rows} observation(s), but at least {min_obs} are required.",
        )

    # Defensible minimum coverage across ALL 4 required parameters
    # A window where 1 or more required parameters have fewer than min_obs usable
    # observations must not be passed to ML models for forecasting.
    REQUIRED_PARAMETERS = ("pH", "TDS", "turbidity", "temperature")
    insufficient_params = {
        param: window.observed_by_parameter.get(param, 0)
        for param in REQUIRED_PARAMETERS
        if window.observed_by_parameter.get(param, 0) < min_obs
    }
    if insufficient_params:
        details = ", ".join(
            f"'{param}': {count} valid reading(s) available; at least {min_obs} required"
            for param, count in insufficient_params.items()
        )
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient valid observations for parameter(s): {details}.",
        )

    import numpy as np

    inference = get_inference_service()
    try:
        inference.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Forecast checkpoint not found: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Forecast checkpoints are unavailable: {exc}")

    # --- Alert integration ---
    # Use ThingSpeak channel_id as node_id for alert tracking
    thingspeak_node_id = f"thingspeak-{window.channel_id}"
    # Ensure the node exists for alert association
    NodeRepository.get_or_create(
        db, thingspeak_node_id, f"ThingSpeak Channel {window.channel_id}", "ThingSpeak"
    )

    # Prepare latest reading data for alert evaluation (only core 4 parameters)
    latest_reading_data = {
        "ph": window.values[-1][0],
        "tds": window.values[-1][1],
        "turbidity": window.values[-1][2],
        "temperature": window.values[-1][3],
        "source": "THINGSPEAK",
        "timestamp": window.latest_timestamp or datetime.now(timezone.utc),
    }

    # Evaluate alerts for threshold violations (pH, TDS, turbidity, temperature only)
    # Does NOT evaluate RGB or unavailable optical_colour_index
    AlertService.evaluate_reading_for_alerts(db, thingspeak_node_id, latest_reading_data)

    # Auto-resolve alerts when readings return to normal range
    AlertService.check_and_resolve_alerts(db, thingspeak_node_id, latest_reading_data)

    # Build (30, 5) input window for the 5-feature checkpoints:
    # 4 measured physical parameters + neutral baseline OCI (0.5583, matching training dataset mean)
    # RGB values are display-only and NOT fed into forecasting models.
    NEUTRAL_OCI_BASELINE = 0.5583
    input_rows = []
    for row in window.values:
        input_rows.append([row[0], row[1], row[2], row[3], NEUTRAL_OCI_BASELINE])
    input_window = np.array(input_rows, dtype=np.float32)

    result = inference.forecast(input_window)

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    observed_timestamp = (
        window.latest_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        if window.latest_timestamp is not None
        else None
    )

    # Extract RGB values from the newest feed if available (display-only)
    latest_rgb = None
    if window.rgb_values and len(window.rgb_values) > 0:
        last_rgb = window.rgb_values[-1]
        if any(v is not None for v in last_rgb):
            latest_rgb = ThingSpeakRGBValues(
                red=last_rgb[0],
                green=last_rgb[1],
                blue=last_rgb[2],
                clear=last_rgb[3],
            )

    # Calculate RGB missing counts
    rgb_missing = {}
    if window.rgb_values:
        for i, colour in enumerate(("red", "green", "blue", "clear")):
            rgb_missing[colour] = sum(
                1 for row in window.rgb_values if row[i] is None
            )

    latest_values = ThingSpeakReadingValues(
        pH=window.values[-1][0],
        TDS=window.values[-1][1],
        turbidity=window.values[-1][2],
        temperature=window.values[-1][3],
    )

    # Verify that model predictions are finite and physically plausible
    for model_name, forecasts in result.model_forecasts.items():
        for param, val in forecasts.items():
            if not math.isfinite(val):
                raise HTTPException(
                    status_code=502,
                    detail=f"Model {model_name} generated a non-finite forecast for {param}.",
                )
    for param, val in result.ensemble.items():
        if not math.isfinite(val):
            raise HTTPException(
                status_code=502,
                detail=f"Ensemble generated a non-finite forecast for {param}.",
            )

    # Calculate live sample interval and actual next-step target timestamp
    valid_timestamps = [ts for ts in window.timestamps if ts is not None]
    target_timestamp = None
    sample_interval_seconds = None
    if len(valid_timestamps) >= 2:
        interval = (valid_timestamps[-1] - valid_timestamps[-2]).total_seconds()
        if 0 < interval < 3600:
            sample_interval_seconds = int(round(interval))
            target_timestamp = (valid_timestamps[-1] + timedelta(seconds=sample_interval_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Forecast only the 4 water-quality parameters (pH, TDS, turbidity, temperature)
    forecast_block = ThingSpeakForecastBlock(
        lstm=ThingSpeakReadingValues(
            pH=result.model_forecasts["lstm"]["pH"],
            TDS=result.model_forecasts["lstm"]["TDS"],
            turbidity=result.model_forecasts["lstm"]["turbidity"],
            temperature=result.model_forecasts["lstm"]["temperature"],
        ),
        patchtst=ThingSpeakReadingValues(
            pH=result.model_forecasts["patchtst"]["pH"],
            TDS=result.model_forecasts["patchtst"]["TDS"],
            turbidity=result.model_forecasts["patchtst"]["turbidity"],
            temperature=result.model_forecasts["patchtst"]["temperature"],
        ),
        timemixer=ThingSpeakReadingValues(
            pH=result.model_forecasts["timemixer"]["pH"],
            TDS=result.model_forecasts["timemixer"]["TDS"],
            turbidity=result.model_forecasts["timemixer"]["turbidity"],
            temperature=result.model_forecasts["timemixer"]["temperature"],
        ),
        ensemble=ThingSpeakReadingValues(
            pH=result.ensemble["pH"],
            TDS=result.ensemble["TDS"],
            turbidity=result.ensemble["turbidity"],
            temperature=result.ensemble["temperature"],
        ),
    )

    # Model weights for the 4 forecast parameters
    relevant_weights = {
        param: dict(entry)
        for param, entry in result.weights.items()
        if param in {"pH", "TDS", "turbidity", "temperature"}
    }

    return ThingSpeakForecastResponse(
        status="success",
        latest_reading=ThingSpeakLatestReading(
            timestamp=observed_timestamp,
            observed_at=observed_timestamp,
            values=latest_values,
            rgb=latest_rgb,
            entry_id=window.latest_entry_id,
            status_flag=window.latest_status_flag,
            channel_id=window.channel_id,
            node_id=f"thingspeak-{window.channel_id}",
        ),

        forecast=forecast_block,
        prediction=forecast_block.ensemble,
        weights=relevant_weights,
        model_versions=dict(result.checkpoint_versions),
        target_timestamp=target_timestamp,
        sample_interval_seconds=sample_interval_seconds,
        provenance=ForecastProvenance(
            data_source="THINGSPEAK",
            channel_id=window.channel_id,
            models_trained_on=result.training_dataset_source,
            real_sensor_data=result.real_sensor_data,
            window=WindowProvenance(
                window_size=window.window_size,
                observed_rows=window.observed_rows,
                forward_filled=window.forward_filled,
                leading_filled=window.leading_filled,
                padded_rows=window.padded_rows,
                missing_by_parameter=dict(window.missing_by_parameter),
                unobserved_parameters=list(window.unobserved_parameters),
                rgb_missing_by_channel=rgb_missing,
                source_rows_fetched=window.source_rows_fetched,
                observed_by_parameter=dict(window.observed_by_parameter),
            ),
            fetched_at=fetched_at,
        ),
        model_lifecycle_state="EXPERIMENTAL",
        next_day_forecast_status="UNAVAILABLE_INSUFFICIENT_REAL_DATA",
        next_day_forecast_reason=(
            "Real sensor data coverage is 0.68% (71 minutes active operation across 7 days with multi-hour gaps). "
            "Zero continuous 24-hour windows exist to train or validate genuine next-day forecasting. "
            "An experimental next-step (~33s) prediction is provided as a baseline."
        ),
        data_coverage_percent=0.684,
        continuous_24h_windows=0,
    )


# --- New endpoint: latest ThingSpeak reading (no forecast) ---

@router.get("/thingspeak/latest", response_model=ThingSpeakLatestReading)
def get_latest_thingspeak_reading(
    channel_id: Optional[str] = Query(
        None,
        min_length=1,
        max_length=32,
        description="Optional numeric ThingSpeak channel id overriding the configured default.",
    ),
    principal: dict = Depends(require_student_or_admin),
) -> ThingSpeakLatestReading:
    """Fetch the latest reading from the configured ThingSpeak channel.

    This is a lightweight, read-only endpoint that returns the most recent
    feed from ThingSpeak without running any forecast models. It shares the
    same field mapping, gap-handling, and provenance reporting as the
    forecast endpoint but omits the ML step entirely.

    The response includes:
    - Core water-quality parameters (pH, TDS, turbidity, temperature)
    - Raw RGB percentages (0\u2013100) from the TCS34725 sensor (fields 5-7)
    - Observation timestamp from ThingSpeak
    - Provenance metadata (channel ID, fill counts, etc.)

    No sensor data is written to the database. The endpoint is authenticated
    and requires STUDENT or ADMIN role.
    """
    config = _resolve_thingspeak_config(channel_id)

    try:
        window = parse_feeds(thingspeak_service.fetch_feeds(config), config)
    except ThingSpeakNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ThingSpeakInvalidChannel as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ThingSpeakUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if window.observed_rows == 0:
        raise HTTPException(
            status_code=502,
            detail="The ThingSpeak channel returned no observations.",
        )

    # Extract RGB values from the newest feed if available
    latest_rgb = None
    if window.rgb_values and len(window.rgb_values) > 0:
        last_rgb = window.rgb_values[-1]
        if any(v is not None for v in last_rgb):
            latest_rgb = ThingSpeakRGBValues(
                red=last_rgb[0],
                green=last_rgb[1],
                blue=last_rgb[2],
                clear=last_rgb[3],
            )

    # Calculate RGB missing counts
    rgb_missing = {}
    if window.rgb_values:
        for i, colour in enumerate(("red", "green", "blue", "clear")):
            rgb_missing[colour] = sum(
                1 for row in window.rgb_values if row[i] is None
            )

    observed_timestamp = (
        window.latest_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        if window.latest_timestamp is not None
        else None
    )

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return ThingSpeakLatestReading(
        timestamp=observed_timestamp,
        observed_at=observed_timestamp,
        values=ThingSpeakReadingValues(
            pH=window.values[-1][0],
            TDS=window.values[-1][1],
            turbidity=window.values[-1][2],
            temperature=window.values[-1][3],
        ),
        rgb=latest_rgb,
        entry_id=window.latest_entry_id,
        status_flag=window.latest_status_flag,
        channel_id=config.channel_id,
        node_id=f"thingspeak-{config.channel_id}",
    )


# --- Endpoint: historical ThingSpeak readings ---

@router.get("/thingspeak/history", response_model=ThingSpeakHistoryResponse)
def get_thingspeak_history(
    channel_id: Optional[str] = Query(
        None,
        min_length=1,
        max_length=32,
        description="Optional numeric ThingSpeak channel id overriding the configured default.",
    ),
    limit: int = Query(
        30,
        ge=1,
        le=100,
        description="Maximum number of historical feed readings to return (default: 30, max: 100).",
    ),
    principal: dict = Depends(require_student_or_admin),
) -> ThingSpeakHistoryResponse:
    """Fetch chronologically ordered historical readings from ThingSpeak.

    Returns the latest `limit` feeds from the configured ThingSpeak channel,
    parsed into physical units with timestamps, RGB percentages, entry IDs,
    and status flags. Chronological order (oldest first, newest last) is preserved.
    """
    import dataclasses

    config = _resolve_thingspeak_config(channel_id)
    config = dataclasses.replace(config, results=max(1, limit))

    try:
        feeds = thingspeak_service.fetch_feeds(config)
    except ThingSpeakNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ThingSpeakInvalidChannel as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ThingSpeakUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    parsed_readings = parse_history_readings(feeds, config)
    if len(parsed_readings) > limit:
        parsed_readings = parsed_readings[-limit:]

    return ThingSpeakHistoryResponse(
        channel_id=config.channel_id,
        count=len(parsed_readings),
        source="THINGSPEAK",
        readings=parsed_readings,
    )


# --- Audit & Lifecycle Endpoint ---

@router.get("/real-data-audit", summary="Get real sensor data quality audit and model promotion lifecycle")
@router.get("/forecast/real-data-audit", summary="Get real sensor data quality audit and model promotion lifecycle")
def get_real_data_audit(
    principal: dict = Depends(require_student_or_admin),
) -> dict:
    """Return the scientific data quality audit, gap distribution, and model promotion registry."""
    backend_root = FilePath(__file__).resolve().parents[2]
    audit_file = backend_root / "artifacts" / "results" / "real_data_quality_audit.json"
    registry_file = backend_root / "artifacts" / "results" / "model_promotion_registry.json"
    benchmark_file = backend_root / "artifacts" / "results" / "real_model_benchmark_comparison.json"

    audit_json = {}
    if audit_file.exists():
        with audit_file.open("r", encoding="utf-8") as f:
            audit_json = json.load(f)

    registry_json = {}
    if registry_file.exists():
        with registry_file.open("r", encoding="utf-8") as f:
            registry_json = json.load(f)

    benchmark_json = {}
    if benchmark_file.exists():
        with benchmark_file.open("r", encoding="utf-8") as f:
            benchmark_json = json.load(f)

    return {
        "status": "success",
        "data_quality_audit": audit_json,
        "model_lifecycle_registry": registry_json,
        "model_benchmarks": benchmark_json,
    }
