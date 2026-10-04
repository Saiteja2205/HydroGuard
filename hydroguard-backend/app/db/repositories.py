"""Repository pattern for database access.

Provides clean data access layer separate from business logic and API routes.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from app.db.models import Alert, EnsembleWeight, Forecast, ModelError, Node, SensorCalibration, SensorReading


class NodeRepository:
    """Repository for node-related database operations."""

    @staticmethod
    def create(db: Session, node_id: str, name: str, location: str, status: str = "offline") -> Node:
        """Create a new node."""
        node = Node(
            node_id=node_id,
            name=name,
            location=location,
            status=status,
        )
        db.add(node)
        db.commit()
        db.refresh(node)
        return node

    @staticmethod
    def get_by_node_id(db: Session, node_id: str) -> Optional[Node]:
        """Get a node by its node_id."""
        return db.query(Node).filter(Node.node_id == node_id).first()

    @staticmethod
    def get_or_create(db: Session, node_id: str, name: str, location: str, status: str = "offline") -> Node:
        """Get existing node or create if it doesn't exist."""
        node = NodeRepository.get_by_node_id(db, node_id)
        if node is None:
            node = NodeRepository.create(db, node_id, name, location, status)
        return node

    @staticmethod
    def update_status(db: Session, node_id: str, status: str) -> Optional[Node]:
        """Update node status."""
        node = NodeRepository.get_by_node_id(db, node_id)
        if node:
            node.status = status
            node.last_seen = datetime.now(timezone.utc)
            db.commit()
            db.refresh(node)
        return node

    @staticmethod
    def list_all(db: Session) -> list[Node]:
        """List all nodes."""
        return db.query(Node).all()


class SensorReadingRepository:
    """Repository for sensor reading database operations."""

    @staticmethod
    def create(
        db: Session,
        node_id: str,
        timestamp: datetime,
        ph: float,
        tds: float,
        turbidity: float,
        temperature: Optional[float] = None,
        red: Optional[int] = None,
        green: Optional[int] = None,
        blue: Optional[int] = None,
        clear: Optional[int] = None,
        optical_colour_index: Optional[float] = None,
        calibration_id: Optional[int] = None,
        source: str = "HISTORICAL_DATA",
    ) -> SensorReading:
        """Create a new sensor reading."""
        reading = SensorReading(
            node_id=node_id,
            timestamp=timestamp,
            ph=ph,
            tds=tds,
            turbidity=turbidity,
            temperature=temperature,
            red=red,
            green=green,
            blue=blue,
            clear=clear,
            optical_colour_index=optical_colour_index,
            calibration_id=calibration_id,
            source=source,
        )
        db.add(reading)
        db.commit()
        db.refresh(reading)
        return reading

    @staticmethod
    def get_latest_by_node(db: Session, node_id: str) -> Optional[SensorReading]:
        """Get the latest reading for a node."""
        return (
            db.query(SensorReading)
            .filter(SensorReading.node_id == node_id)
            .order_by(desc(SensorReading.timestamp))
            .first()
        )

    @staticmethod
    def get_history_by_node(
        db: Session,
        node_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[SensorReading]:
        """Get historical readings for a node."""
        query = db.query(SensorReading).filter(SensorReading.node_id == node_id)

        if start:
            query = query.filter(SensorReading.timestamp >= start)
        if end:
            query = query.filter(SensorReading.timestamp <= end)

        query = query.order_by(desc(SensorReading.timestamp))
        if limit:
            return list(reversed(query.limit(limit).all()))
        return list(reversed(query.all()))

    @staticmethod
    def get_count_by_node(db: Session, node_id: str) -> int:
        """Get the count of readings for a node."""
        return db.query(SensorReading).filter(SensorReading.node_id == node_id).count()

    @staticmethod
    def delete_by_node(db: Session, node_id: str) -> int:
        """Delete all readings for a node."""
        count = db.query(SensorReading).filter(SensorReading.node_id == node_id).count()
        db.query(SensorReading).filter(SensorReading.node_id == node_id).delete()
        db.commit()
        return count


class ForecastRepository:
    """Repository for forecast database operations."""

    @staticmethod
    def create(
        db: Session,
        node_id: str,
        forecast_date: datetime,
        lstm_predictions: dict[str, float],
        patchtst_predictions: dict[str, float],
        timemixer_predictions: dict[str, float],
        ensemble_predictions: dict[str, float],
        weights: dict[str, dict[str, float]],
        input_start: Optional[datetime] = None,
        input_end: Optional[datetime] = None,
        data_source: str = "HISTORICAL_DATA",
        model_versions: Optional[dict[str, str]] = None,
        weight_strategy: str = "initial",
        horizon_hours: int = 24,
    ) -> Forecast:
        """Create a new forecast record."""
        forecast = Forecast(
            node_id=node_id,
            forecast_date=forecast_date,
            horizon_hours=horizon_hours,
            input_start=input_start,
            input_end=input_end,
            data_source=data_source,
            model_versions=model_versions or {},
            weight_strategy=weight_strategy,
            # LSTM predictions
            lstm_ph=lstm_predictions.get("pH", 0.0),
            lstm_tds=lstm_predictions.get("TDS", 0.0),
            lstm_turbidity=lstm_predictions.get("turbidity", 0.0),
            lstm_temperature=lstm_predictions.get("temperature"),
            # PatchTST predictions
            patchtst_ph=patchtst_predictions.get("pH", 0.0),
            patchtst_tds=patchtst_predictions.get("TDS", 0.0),
            patchtst_turbidity=patchtst_predictions.get("turbidity", 0.0),
            patchtst_temperature=patchtst_predictions.get("temperature"),
            # TimeMixer predictions
            timemixer_ph=timemixer_predictions.get("pH", 0.0),
            timemixer_tds=timemixer_predictions.get("TDS", 0.0),
            timemixer_turbidity=timemixer_predictions.get("turbidity", 0.0),
            timemixer_temperature=timemixer_predictions.get("temperature"),
            # Ensemble predictions
            ensemble_ph=ensemble_predictions.get("pH", 0.0),
            ensemble_tds=ensemble_predictions.get("TDS", 0.0),
            ensemble_turbidity=ensemble_predictions.get("turbidity", 0.0),
            ensemble_temperature=ensemble_predictions.get("temperature"),
            # Model weights for pH
            lstm_weight_ph=weights.get("pH", {}).get("LSTM", 0.33),
            patchtst_weight_ph=weights.get("pH", {}).get("PatchTST", 0.33),
            timemixer_weight_ph=weights.get("pH", {}).get("TimeMixer", 0.34),
            # Model weights for TDS
            lstm_weight_tds=weights.get("TDS", {}).get("LSTM", 0.33),
            patchtst_weight_tds=weights.get("TDS", {}).get("PatchTST", 0.33),
            timemixer_weight_tds=weights.get("TDS", {}).get("TimeMixer", 0.34),
            # Model weights for turbidity
            lstm_weight_turbidity=weights.get("turbidity", {}).get("LSTM", 0.33),
            patchtst_weight_turbidity=weights.get("turbidity", {}).get("PatchTST", 0.33),
            timemixer_weight_turbidity=weights.get("turbidity", {}).get("TimeMixer", 0.34),
            # Model weights for temperature
            lstm_weight_temperature=weights.get("temperature", {}).get("LSTM", 0.33),
            patchtst_weight_temperature=weights.get("temperature", {}).get("PatchTST", 0.33),
            timemixer_weight_temperature=weights.get("temperature", {}).get("TimeMixer", 0.34),
        )
        db.add(forecast)
        db.commit()
        db.refresh(forecast)
        return forecast

    @staticmethod
    def get_by_node(db: Session, node_id: str, limit: Optional[int] = None) -> list[Forecast]:
        """Get forecasts for a node."""
        query = (
            db.query(Forecast)
            .filter(Forecast.node_id == node_id)
            .order_by(desc(Forecast.forecast_date))
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def get_by_date(db: Session, node_id: str, forecast_date: datetime) -> Optional[Forecast]:
        """Get a forecast by node and forecast date."""
        return (
            db.query(Forecast)
            .filter(and_(Forecast.node_id == node_id, Forecast.forecast_date == forecast_date))
            .first()
        )

    @staticmethod
    def get_targeting_day(db: Session, node_id: str, target_date: datetime) -> list[Forecast]:
        """Return forecasts whose target falls on the observation's calendar day."""
        return db.query(Forecast).filter(
            Forecast.node_id == node_id,
            func.date(Forecast.forecast_date) == target_date.date().isoformat(),
        ).all()

    @staticmethod
    def get_latest_by_node(db: Session, node_id: str) -> Optional[Forecast]:
        """Get the latest forecast for a node."""
        return (
            db.query(Forecast)
            .filter(Forecast.node_id == node_id)
            .order_by(desc(Forecast.forecast_date))
            .first()
        )


class ModelErrorRepository:
    """Repository for model error database operations."""

    @staticmethod
    def create(
        db: Session,
        node_id: str,
        forecast_id: Optional[int],
        forecast_date: datetime,
        model_name: str,
        parameter: str,
        predicted_value: float,
        actual_value: float,
        absolute_error: float,
        squared_error: float,
        mae: Optional[float] = None,
        rmse: Optional[float] = None,
        actual_timestamp: Optional[datetime] = None,
        evaluated_at: Optional[datetime] = None,
        data_source: str = "HISTORICAL_DATA",
        mape: Optional[float] = None,
        horizon_hours: int = 24,
    ) -> ModelError:
        """Create a new model error record."""
        error = ModelError(
            node_id=node_id,
            forecast_id=forecast_id,
            forecast_date=forecast_date,
            horizon_hours=horizon_hours,
            model_name=model_name,
            parameter=parameter,
            predicted_value=predicted_value,
            actual_value=actual_value,
            absolute_error=absolute_error,
            squared_error=squared_error,
            mae=mae,
            rmse=rmse,
            actual_timestamp=actual_timestamp,
            evaluated_at=evaluated_at or datetime.now(timezone.utc),
            data_source=data_source,
            mape=mape,
        )
        db.add(error)
        db.commit()
        db.refresh(error)
        return error

    @staticmethod
    def get_by_node(
        db: Session,
        node_id: str,
        model_name: Optional[str] = None,
        parameter: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[ModelError]:
        """Get model errors for a node."""
        query = db.query(ModelError).filter(ModelError.node_id == node_id)

        if model_name:
            query = query.filter(ModelError.model_name == model_name)
        if parameter:
            query = query.filter(ModelError.parameter == parameter)

        query = query.order_by(desc(ModelError.forecast_date))

        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def get_average_errors(
        db: Session,
        node_id: str,
        model_name: Optional[str] = None,
        parameter: Optional[str] = None,
    ) -> dict[str, dict[str, float]]:
        """Get average MAE and RMSE for models and parameters."""
        query = db.query(
            ModelError.model_name,
            ModelError.parameter,
            func.avg(ModelError.mae).label("avg_mae"),
            func.avg(ModelError.rmse).label("avg_rmse"),
            func.count(ModelError.id).label("count"),
        ).filter(ModelError.node_id == node_id)

        if model_name:
            query = query.filter(ModelError.model_name == model_name)
        if parameter:
            query = query.filter(ModelError.parameter == parameter)

        results = query.group_by(ModelError.model_name, ModelError.parameter).all()

        avg_errors = {}
        for row in results:
            if row.model_name not in avg_errors:
                avg_errors[row.model_name] = {}
            avg_errors[row.model_name][row.parameter] = {
                "mae": float(row.avg_mae) if row.avg_mae else 0.0,
                "rmse": float(row.avg_rmse) if row.avg_rmse else 0.0,
                "count": row.count,
            }

        return avg_errors

    @staticmethod
    def get_recent_errors(
        db: Session,
        node_id: str,
        model_name: Optional[str] = None,
        parameter: Optional[str] = None,
        window_size: int = 30,
        data_source: Optional[str] = None,
        horizon_hours: Optional[int] = None,
    ) -> list[ModelError]:
        """Get recent errors for ensemble weight calculation."""
        query = db.query(ModelError).filter(ModelError.node_id == node_id)

        if model_name:
            query = query.filter(ModelError.model_name == model_name)
        if parameter:
            query = query.filter(ModelError.parameter == parameter)
        if data_source:
            query = query.filter(ModelError.data_source == data_source)
        if horizon_hours is not None:
            query = query.filter(ModelError.horizon_hours == horizon_hours)

        query = query.order_by(desc(ModelError.forecast_date)).limit(window_size)

        return query.all()


class EnsembleWeightRepository:
    @staticmethod
    def get_by_node(db: Session, node_id: str, data_source: Optional[str] = None) -> list[EnsembleWeight]:
        query = db.query(EnsembleWeight).filter(EnsembleWeight.node_id == node_id)
        if data_source is not None:
            query = query.filter(EnsembleWeight.data_source == data_source)
        return query.all()

    @staticmethod
    def set_weight(db: Session, node_id: str, parameter: str, model_name: str, weight: float, observations: int, data_source: str = "HISTORICAL_DATA") -> None:
        row = db.query(EnsembleWeight).filter_by(
            node_id=node_id, parameter=parameter, model_name=model_name, data_source=data_source
        ).first()
        if row is None:
            row = EnsembleWeight(node_id=node_id, parameter=parameter, model_name=model_name, data_source=data_source, weight=weight, observations=observations)
            db.add(row)
        else:
            row.weight = weight
            row.observations = observations
            row.updated_at = datetime.now(timezone.utc)
        db.commit()


class SensorCalibrationRepository:
    @staticmethod
    def create(db: Session, node_id: str, sensor: str, calibrated_at: datetime, reference_sample: str, metadata: dict) -> SensorCalibration:
        row = SensorCalibration(node_id=node_id, sensor=sensor, calibrated_at=calibrated_at,
                                reference_sample=reference_sample, metadata_json=metadata)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


class AlertRepository:
    """Repository for alert database operations."""

    @staticmethod
    def create(
        db: Session,
        node_id: str,
        timestamp: datetime,
        parameter: str,
        value: float,
        threshold: float,
        severity: str = "WARNING",
        message: str = "",
        status: str = "ACTIVE",
    ) -> Alert:
        """Create a new alert."""
        alert = Alert(
            node_id=node_id,
            timestamp=timestamp,
            parameter=parameter,
            value=value,
            threshold=threshold,
            severity=severity,
            message=message,
            status=status,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def get_by_node(
        db: Session,
        node_id: str,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Alert]:
        """Get alerts for a node."""
        query = db.query(Alert).filter(Alert.node_id == node_id)

        if status:
            query = query.filter(Alert.status == status)

        query = query.order_by(desc(Alert.timestamp))

        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    def update_status(db: Session, alert_id: int, status: str) -> Optional[Alert]:
        """Update alert status."""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.status = status
            db.commit()
            db.refresh(alert)
        return alert

    @staticmethod
    def get_active_by_node(db: Session, node_id: str) -> list[Alert]:
        """Get active alerts for a node."""
        return (
            db.query(Alert)
            .filter(and_(Alert.node_id == node_id, Alert.status == "ACTIVE"))
            .order_by(desc(Alert.timestamp))
            .all()
        )
