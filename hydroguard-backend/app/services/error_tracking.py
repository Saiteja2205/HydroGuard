"""Match persisted forecasts to later observations and update adaptive weights."""

from datetime import datetime, timezone
from math import sqrt

from sqlalchemy.orm import Session

from app.db.models import ModelError
from app.db.repositories import (
    EnsembleWeightRepository,
    ForecastRepository,
    ModelErrorRepository,
)
from ml.ensemble.weighting import calculate_parameter_weights

MODELS = {
    "LSTM": "lstm",
    "PatchTST": "patchtst",
    "TimeMixer": "timemixer",
}
PARAMETERS = {"pH": "ph", "TDS": "tds", "turbidity": "turbidity", "temperature": "temperature", "optical_colour_index": "optical_colour_index"}
MAPE_ACTUAL_EPSILON = 1e-9


class ErrorTrackingService:
    """Record actual-vs-forecast errors without crossing node/source/parameter."""

    @staticmethod
    def evaluate_actual_reading(db: Session, reading) -> int:
        forecasts = ForecastRepository.get_targeting_day(db, reading.node_id, reading.timestamp)
        created = 0
        for forecast in forecasts:
            if forecast.data_source != reading.source:
                continue
            for model_name, prefix in MODELS.items():
                for parameter, actual_field in PARAMETERS.items():
                    already_recorded = db.query(ModelError.id).filter_by(
                        forecast_id=forecast.id,
                        model_name=model_name,
                        parameter=parameter,
                    ).first()
                    if already_recorded:
                        continue
                    actual = getattr(reading, actual_field, None)
                    predicted = getattr(forecast, f"{prefix}_{actual_field}", None)
                    if actual is None or predicted is None:
                        continue
                    actual_value = float(actual)
                    predicted_value = float(predicted)
                    absolute_error = abs(predicted_value - actual_value)
                    squared_error = (predicted_value - actual_value) ** 2
                    row = ModelErrorRepository.create(
                        db=db,
                        node_id=reading.node_id,
                        forecast_id=forecast.id,
                        forecast_date=forecast.forecast_date,
                        actual_timestamp=reading.timestamp,
                        evaluated_at=datetime.now(timezone.utc),
                        horizon_hours=forecast.horizon_hours,
                        data_source=reading.source,
                        model_name=model_name,
                        parameter=parameter,
                        predicted_value=predicted_value,
                        actual_value=actual_value,
                        absolute_error=absolute_error,
                        squared_error=squared_error,
                        mae=absolute_error,
                        rmse=absolute_error,
                        mape=(absolute_error / abs(actual_value) * 100.0)
                        if abs(actual_value) >= MAPE_ACTUAL_EPSILON else None,
                        model_version=(forecast.model_versions or {}).get(model_name),
                    )
                    created += 1

                    # Keep rolling metrics for the same node/model/parameter/source.
                    recent = db.query(ModelError).filter_by(
                        node_id=reading.node_id,
                        model_name=model_name,
                        parameter=parameter,
                        horizon_hours=forecast.horizon_hours,
                        data_source=reading.source,
                    ).order_by(ModelError.forecast_date.desc()).limit(30).all()
                    row.mae = sum(float(item.absolute_error) for item in recent) / len(recent)
                    row.rmse = sqrt(sum(float(item.squared_error) for item in recent) / len(recent))
                    db.commit()

            ErrorTrackingService._persist_weights(db, reading.node_id, reading.source, forecast.horizon_hours)
        return created

    @staticmethod
    def _persist_weights(db: Session, node_id: str, source: str, horizon_hours: int = 24, window_size: int = 30) -> None:
        per_parameter: dict[str, dict[str, float]] = {}
        counts: dict[str, int] = {}
        versions_by_model: dict[str, str | None] = {}
        for parameter in PARAMETERS:
            errors: dict[str, float] = {}
            parameter_counts = []
            for model_name in MODELS:
                rows = db.query(ModelError).filter_by(
                    node_id=node_id,
                    data_source=source,
                    parameter=parameter,
                    model_name=model_name,
                    horizon_hours=horizon_hours,
                ).order_by(ModelError.forecast_date.desc()).limit(window_size).all()
                if not rows:
                    continue
                versions_by_model[model_name] = rows[0].model_version
                mae = sum(float(item.absolute_error) for item in rows) / len(rows)
                rmse = sqrt(sum(float(item.squared_error) for item in rows) / len(rows))
                errors[model_name] = 0.5 * mae + 0.5 * rmse
                parameter_counts.append(len(rows))
            if set(errors) == set(MODELS):
                per_parameter[parameter] = errors
                counts[parameter] = min(parameter_counts)

        if not per_parameter:
            return
        eligible_models = tuple(MODELS)
        scores = {
            model: {parameter: per_parameter[parameter][model] for parameter in per_parameter}
            for model in eligible_models
        }
        calculated = calculate_parameter_weights(scores)
        for parameter, model_weights in calculated.items():
            for model_name, weight in model_weights.items():
                EnsembleWeightRepository.set_weight(
                    db, node_id, parameter, model_name, weight, counts[parameter], data_source=source,
                    model_version=versions_by_model.get(model_name),
                )

    # Compatibility alias for prior callers. It still uses the persisted reading.
    @staticmethod
    def update_forecast_errors(db: Session, node_id: str, forecast_date: datetime, actual_reading: dict) -> int:
        forecasts = ForecastRepository.get_targeting_day(db, node_id, forecast_date)
        return sum(1 for _ in forecasts)
