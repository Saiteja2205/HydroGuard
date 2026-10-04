"""Admin-only CSV export of stored observations and forecast evaluations."""

import csv
import json
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import require_roles
from app.db import get_db
from app.db.models import Alert, Forecast, ModelError, SensorCalibration, SensorReading

router = APIRouter(prefix="/research", tags=["research-export"])
PARAMETERS = {"pH": ("ph", "PH"), "TDS": ("tds", "TDS"), "turbidity": ("turbidity", "TURBIDITY"), "temperature": ("temperature", "TEMPERATURE")}
MODELS = {"LSTM": "lstm", "PatchTST": "patchtst", "TimeMixer": "timemixer"}
COLUMNS = [
    "record_type", "timestamp", "target_timestamp", "node_id", "data_source", "parameter",
    "ph", "tds", "turbidity", "temperature", "red", "green", "blue", "clear",
    "optical_colour_index", "calibration_id", "calibration_sensor", "calibration_timestamp",
    "calibration_reference", "calibration_metadata", "forecast", "ensemble_forecast", "actual",
    "model", "model_version", "forecast_horizon_hours", "mae", "rmse", "mape",
    "ensemble_weight", "anomaly_information", "threshold_event",
]


@router.get("/export.csv")
def export_research_csv(
    node_id: str | None = Query(None, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"),
    start: datetime | None = None,
    end: datetime | None = None,
    _: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    readings_query = db.query(SensorReading)
    forecasts_query = db.query(Forecast)
    alerts_query = db.query(Alert)
    if node_id:
        readings_query = readings_query.filter(SensorReading.node_id == node_id)
        forecasts_query = forecasts_query.filter(Forecast.node_id == node_id)
        alerts_query = alerts_query.filter(Alert.node_id == node_id)
    if start:
        readings_query = readings_query.filter(SensorReading.timestamp >= start)
        forecasts_query = forecasts_query.filter(Forecast.forecast_date >= start)
        alerts_query = alerts_query.filter(Alert.timestamp >= start)
    if end:
        readings_query = readings_query.filter(SensorReading.timestamp <= end)
        forecasts_query = forecasts_query.filter(Forecast.forecast_date <= end)
        alerts_query = alerts_query.filter(Alert.timestamp <= end)

    readings = readings_query.order_by(SensorReading.timestamp.asc()).limit(10000).all()
    forecasts = forecasts_query.order_by(Forecast.forecast_date.asc()).limit(10000).all()
    alerts = alerts_query.order_by(Alert.timestamp.asc()).limit(10000).all()
    calibration_ids = {reading.calibration_id for reading in readings if reading.calibration_id is not None}
    calibrations = {
        item.id: item for item in db.query(SensorCalibration).filter(SensorCalibration.id.in_(calibration_ids)).all()
    } if calibration_ids else {}
    forecast_ids = [item.id for item in forecasts]
    errors = db.query(ModelError).filter(ModelError.forecast_id.in_(forecast_ids)).all() if forecast_ids else []
    errors_by_key = {(item.forecast_id, item.model_name, item.parameter): item for item in errors}

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for reading in readings:
        calibration = calibrations.get(reading.calibration_id)
        row = {
            "record_type": "reading", "timestamp": reading.timestamp.isoformat(), "node_id": reading.node_id,
            "data_source": reading.source, "ph": reading.ph, "tds": reading.tds,
            "turbidity": reading.turbidity, "temperature": reading.temperature,
            "red": reading.red, "green": reading.green, "blue": reading.blue, "clear": reading.clear,
            "optical_colour_index": reading.optical_colour_index, "calibration_id": reading.calibration_id,
            "calibration_sensor": calibration.sensor if calibration else None,
            "calibration_timestamp": calibration.calibrated_at.isoformat() if calibration else None,
            "calibration_reference": calibration.reference_sample if calibration else None,
            "calibration_metadata": json.dumps(calibration.metadata_json, sort_keys=True) if calibration else None,
        }
        events = [
            f"{alert.parameter}:{alert.severity}:{alert.message}"
            for alert in alerts
            if alert.node_id == reading.node_id and alert.timestamp.date() == reading.timestamp.date()
        ]
        row["anomaly_information"] = " | ".join(events) or None
        row["threshold_event"] = " | ".join(events) or None
        writer.writerow(row)

    for forecast in forecasts:
        target_reading = next((
            reading for reading in readings
            if reading.node_id == forecast.node_id
            and reading.source == forecast.data_source
            and reading.timestamp.date() == forecast.forecast_date.date()
        ), None)
        for parameter, (actual_field, parameter_key) in PARAMETERS.items():
            for model_name, prefix in MODELS.items():
                error = errors_by_key.get((forecast.id, model_name, parameter))
                weight_field = f"{prefix}_weight_{parameter_key.lower()}"
                if parameter == "pH":
                    weight_field = f"{prefix}_weight_ph"
                row = {
                    "record_type": "forecast_evaluation", "timestamp": forecast.created_at.isoformat(),
                    "target_timestamp": forecast.forecast_date.isoformat(), "node_id": forecast.node_id,
                    "data_source": forecast.data_source, "parameter": parameter,
                    "forecast": getattr(forecast, f"{prefix}_{actual_field}"),
                    "ensemble_forecast": getattr(forecast, f"ensemble_{actual_field}"),
                    "actual": error.actual_value if error else getattr(target_reading, actual_field, None),
                    "model": model_name, "model_version": (forecast.model_versions or {}).get(model_name),
                    "forecast_horizon_hours": forecast.horizon_hours,
                    "mae": error.mae if error else None, "rmse": error.rmse if error else None,
                    "mape": error.mape if error else None,
                    "ensemble_weight": getattr(forecast, weight_field),
                }
                if target_reading:
                    row.update({
                        "ph": target_reading.ph, "tds": target_reading.tds,
                        "turbidity": target_reading.turbidity, "temperature": target_reading.temperature,
                        "red": target_reading.red, "green": target_reading.green,
                        "blue": target_reading.blue, "clear": target_reading.clear,
                        "optical_colour_index": target_reading.optical_colour_index,
                        "calibration_id": target_reading.calibration_id,
                    })
                target_alerts = [f"{alert.parameter}:{alert.severity}:{alert.message}" for alert in alerts if alert.node_id == forecast.node_id and alert.timestamp.date() == forecast.forecast_date.date()]
                row["anomaly_information"] = " | ".join(target_alerts) or None
                row["threshold_event"] = " | ".join(target_alerts) or None
                writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hydroguard-research-export.csv"},
    )
