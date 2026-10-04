"""SQLAlchemy ORM models for HydroGuard database.

Defines database tables:
- nodes: Sensor node information
- sensor_readings: Water quality telemetry
- forecasts: ML forecast storage
- model_errors: Model performance tracking
- alerts: Alert generation and storage
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import Base from database module to ensure single instance
from app.db.database import Base


class Node(Base):
    """Sensor node information."""

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="offline")
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    sensor_readings: Mapped[list["SensorReading"]] = relationship(
        "SensorReading", back_populates="node", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list["Forecast"]] = relationship(
        "Forecast", back_populates="node", cascade="all, delete-orphan"
    )
    model_errors: Mapped[list["ModelError"]] = relationship(
        "ModelError", back_populates="node", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="node", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Node(node_id='{self.node_id}', name='{self.name}', status='{self.status}')>"


class SensorReading(Base):
    """Water quality sensor readings.

    Active contract: pH, TDS, turbidity, temperature, raw TCS34725 RGB/clear,
    experimental optical colour index, source, node, and timestamp.
    Deprecated legacy columns remain mapped solely to read old databases.
    """

    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("nodes.node_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Four required parameters (current development mode)
    ph: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    tds: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    turbidity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)

    # Deprecated legacy columns retained for historical database compatibility.
    ec: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    do: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Additional metrics
    flow_rate: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Raw TCS34725 counts are retained independently from any derived index.
    red: Mapped[int | None] = mapped_column(Integer, nullable=True)
    green: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Experimental only; no validated color calibration methodology exists yet.
    optical_colour_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_id: Mapped[int | None] = mapped_column(ForeignKey("sensor_calibrations.id"), nullable=True)

    # Data source tracking
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="HISTORICAL_DATA")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    node: Mapped["Node"] = relationship("Node", back_populates="sensor_readings")

    # Composite index for efficient queries
    __table_args__ = (
        Index("idx_sensor_readings_node_timestamp", "node_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<SensorReading(node_id='{self.node_id}', timestamp='{self.timestamp}', ph={self.ph})>"


class Forecast(Base):
    """ML forecast storage.

    Stores individual model predictions, ensemble predictions, and model weights.
    """

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("nodes.node_id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    forecast_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    input_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="HISTORICAL_DATA")
    model_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weight_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="initial")

    # LSTM predictions
    lstm_ph: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    lstm_tds: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    lstm_turbidity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    lstm_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)

    # PatchTST predictions
    patchtst_ph: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    patchtst_tds: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    patchtst_turbidity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    patchtst_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)

    # TimeMixer predictions
    timemixer_ph: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    timemixer_tds: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    timemixer_turbidity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    timemixer_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)

    # Ensemble predictions
    ensemble_ph: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    ensemble_tds: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    ensemble_turbidity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    ensemble_temperature: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    lstm_optical_colour_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    patchtst_optical_colour_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    timemixer_optical_colour_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    ensemble_optical_colour_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Model weights for pH
    lstm_weight_ph: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    patchtst_weight_ph: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    timemixer_weight_ph: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    # Model weights for TDS
    lstm_weight_tds: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    patchtst_weight_tds: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    timemixer_weight_tds: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    # Model weights for turbidity
    lstm_weight_turbidity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    patchtst_weight_turbidity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    timemixer_weight_turbidity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    # Model weights for temperature
    lstm_weight_temperature: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    patchtst_weight_temperature: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    timemixer_weight_temperature: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    lstm_weight_optical_colour_index: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.33)
    patchtst_weight_optical_colour_index: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.33)
    timemixer_weight_optical_colour_index: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.34)

    # Relationships
    node: Mapped["Node"] = relationship("Node", back_populates="forecasts")

    # Composite index for efficient queries
    __table_args__ = (
        Index("idx_forecasts_node_forecast_date", "node_id", "forecast_date"),
    )

    def __repr__(self) -> str:
        return f"<Forecast(node_id='{self.node_id}', forecast_date='{self.forecast_date}')>"


class ModelError(Base):
    """Model error tracking for adaptive ensemble.

    Stores forecast errors for weight adaptation.
    """

    __tablename__ = "model_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("nodes.node_id"), nullable=False, index=True
    )
    forecast_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("forecasts.id"), nullable=True, index=True
    )
    forecast_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    actual_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="HISTORICAL_DATA")
    model_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parameter: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    predicted_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    actual_value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    absolute_error: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    squared_error: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    mae: Mapped[float] = mapped_column(Numeric(10, 4), nullable=True)
    rmse: Mapped[float] = mapped_column(Numeric(10, 4), nullable=True)

    mape: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    node: Mapped["Node"] = relationship("Node", back_populates="model_errors")

    # Composite index for efficient queries
    __table_args__ = (
        Index(
            "idx_model_errors_node_model_param_date",
            "node_id",
            "model_name",
            "parameter",
            "forecast_date",
        ),
    )

    def __repr__(self) -> str:
        return f"<ModelError(model_name='{self.model_name}', parameter='{self.parameter}', mae={self.mae})>"


class EnsembleWeight(Base):
    """Latest persisted adaptive weight, isolated by node and parameter."""

    __tablename__ = "ensemble_weights"
    __table_args__ = (UniqueConstraint("node_id", "parameter", "model_name", "data_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), ForeignKey("nodes.node_id"), nullable=False, index=True)
    parameter: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="HISTORICAL_DATA")
    weight: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class SensorCalibration(Base):
    """Research record for sensor calibration/reference procedures."""

    __tablename__ = "sensor_calibrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64), ForeignKey("nodes.node_id"), nullable=False, index=True)
    sensor: Mapped[str] = mapped_column(String(64), nullable=False)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reference_sample: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Alert(Base):
    """Alert generation and storage.

    Stores alerts for water quality parameter violations.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("nodes.node_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    parameter: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    threshold: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="WARNING")
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    node: Mapped["Node"] = relationship("Node", back_populates="alerts")

    # Composite index for efficient queries
    __table_args__ = (
        Index("idx_alerts_node_timestamp", "node_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Alert(node_id='{self.node_id}', parameter='{self.parameter}', severity='{self.severity}')>"
