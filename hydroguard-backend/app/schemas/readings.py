from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

DataSource = Literal["REAL_SENSOR", "SIMULATED_DEVELOPMENT", "HISTORICAL_DATA", "DEMO", "SIMULATED"]
PRODUCT_PARAMETERS = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")


def normalize_data_source(value: str) -> str:
    return {
        "esp32": "REAL_SENSOR",
        "thingspeak": "REAL_SENSOR",
        "manual": "HISTORICAL_DATA",
        "historical_demo": "DEMO",
        "historical_or_simulated": "DEMO",
        "simulated": "SIMULATED",
        "simulated_development": "SIMULATED_DEVELOPMENT",
    }.get(str(value).strip().lower(), str(value).strip().upper())


def serialize_utc_timestamp(value: datetime) -> str:
    """SQLite returns UTC columns as naive datetimes; interpret them as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ModelsLoadedStatus(BaseModel):
    lstm: bool = False
    patchtst: bool = False
    timemixer: bool = False


class DatabaseHealth(BaseModel):
    """Whether the configured database answered a minimal, bounded check.

    The check runs on a worker thread with a configured timeout so a slow or
    locked database degrades this field instead of hanging a public probe.
    """

    state: Literal["ok", "unavailable"]
    latency_ms: Optional[float] = None
    detail: Optional[str] = None


class ModelHealth(BaseModel):
    """Forecast model availability, read from an already-constructed service.

    Health never loads checkpoints: loading is expensive and would make this
    endpoint slow. ``state`` is therefore ``not_loaded`` until a forecast has
    actually been served, which is honest rather than a fabricated failure.
    """

    state: Literal["loaded", "not_loaded", "unavailable"]
    lstm: bool = False
    patchtst: bool = False
    timemixer: bool = False
    detail: Optional[str] = None


class SensorIngestionHealth(BaseModel):
    """Verified ingestion heartbeat for physical-sensor provenance only.

    Only REAL_SENSOR rows count. Simulated, historical or demo rows are never
    treated as evidence that hardware is attached, so a dashboard built on
    simulated data cannot claim connected sensors.
    """

    state: Literal["recent", "stale", "not_configured"]
    last_real_sensor_at: Optional[str] = None
    age_seconds: Optional[int] = None
    detail: Optional[str] = None


class DataFreshnessHealth(BaseModel):
    """Age and provenance of the newest stored observation."""

    state: Literal["fresh", "stale", "empty"]
    latest_observed_at: Optional[str] = None
    age_seconds: Optional[int] = None
    source: Optional[str] = None
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Liveness plus separately-triaged dependency states.

    ``status`` stays ``ok`` while the HTTP service can answer, because clients
    already key on it. Nothing here implies physical sensors are attached:
    that is reported independently by ``sensor_ingestion``.
    """

    status: Literal["ok"]
    service: str
    version: str
    sensors_connected: bool
    models_loaded: ModelsLoadedStatus
    data_mode: Literal["historical_or_simulated"]
    checked_at: str
    environment: str
    database: DatabaseHealth
    models: ModelHealth
    sensor_ingestion: SensorIngestionHealth
    data_freshness: DataFreshnessHealth


class LatestReadingResponse(BaseModel):
    """Five-parameter product reading. Optical index is experimental."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    timestamp: datetime
    ph: float = Field(..., ge=0.0, le=14.0, allow_inf_nan=False)
    tds: float = Field(..., ge=0.0, le=100_000.0, allow_inf_nan=False)
    turbidity: float = Field(..., ge=0.0, le=10_000.0, allow_inf_nan=False)
    temperature: Optional[float] = Field(default=None, ge=-20.0, le=80.0, allow_inf_nan=False)
    red: Optional[int] = Field(default=None, ge=0, le=65535)
    green: Optional[int] = Field(default=None, ge=0, le=65535)
    blue: Optional[int] = Field(default=None, ge=0, le=65535)
    clear: Optional[int] = Field(default=None, ge=0, le=65535)
    optical_colour_index: Optional[float] = Field(default=None, allow_inf_nan=False)
    calibration_id: Optional[int] = None
    source: DataSource

    @field_validator("source", mode="before")
    @classmethod
    def normalize_legacy_source(cls, value: str) -> str:
        return normalize_data_source(value)

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return serialize_utc_timestamp(value)


class ReadingCreate(BaseModel):
    """Request for creating a sensor reading."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    timestamp: datetime
    ph: float = Field(..., ge=0.0, le=14.0, allow_inf_nan=False)
    tds: float = Field(..., ge=0.0, le=100_000.0, allow_inf_nan=False)
    turbidity: float = Field(..., ge=0.0, le=10_000.0, allow_inf_nan=False)
    temperature: float = Field(..., ge=-20.0, le=80.0, allow_inf_nan=False)
    red: Optional[int] = Field(default=None, ge=0, le=65535)
    green: Optional[int] = Field(default=None, ge=0, le=65535)
    blue: Optional[int] = Field(default=None, ge=0, le=65535)
    clear: Optional[int] = Field(default=None, ge=0, le=65535)
    optical_colour_index: Optional[float] = Field(default=None, allow_inf_nan=False)
    calibration_id: Optional[int] = None
    source: DataSource

    @field_validator("source", mode="before")
    @classmethod
    def normalize_legacy_source(cls, value: str) -> str:
        return normalize_data_source(value)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Reading timestamp must include a timezone.")
        return value

    # Modest device clock skew is tolerated, but an implausibly future-dated
    # sample is rejected instead of being stored as the newest observation.
    # Selection ordering (live provenance before timestamp) is the second
    # line of defence: it keeps a near-future simulated row from masking a
    # legitimate live reading.
    MAX_FUTURE_SKEW: ClassVar[timedelta] = timedelta(hours=24)

    @field_validator("timestamp")
    @classmethod
    def timestamp_not_implausibly_future(cls, value: datetime) -> datetime:
        skew = value.astimezone(timezone.utc) - datetime.now(timezone.utc)
        if skew > cls.MAX_FUTURE_SKEW:
            raise ValueError(
                "Reading timestamp is more than 24 hours in the future; "
                "check the sensor clock before resubmitting."
            )
        return value


class ReadingResponse(BaseModel):
    """Response for reading creation endpoint."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    node_id: str
    timestamp: datetime
    ph: float
    tds: float
    turbidity: float
    temperature: Optional[float] = None
    red: Optional[int] = None
    green: Optional[int] = None
    blue: Optional[int] = None
    clear: Optional[int] = None
    optical_colour_index: Optional[float] = Field(default=None, allow_inf_nan=False)
    calibration_id: Optional[int] = None
    source: str
    created_at: datetime

    @field_validator("source", mode="before")
    @classmethod
    def normalize_legacy_source(cls, value: str) -> str:
        return normalize_data_source(value)

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return serialize_utc_timestamp(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return serialize_utc_timestamp(value)

class HistoryResponse(BaseModel):
    """Response for history endpoint."""

    readings: list[ReadingResponse]
    count: int


class ForecastReading(BaseModel):
    """Single water quality reading for forecast input."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    pH: float = Field(..., ge=0.0, le=14.0, allow_inf_nan=False)
    TDS: float = Field(..., ge=0.0, le=100_000.0, allow_inf_nan=False)
    turbidity: float = Field(..., ge=0.0, le=10_000.0, allow_inf_nan=False)
    temperature: float = Field(..., ge=-20.0, le=80.0, allow_inf_nan=False)
    red: Optional[int] = Field(default=None, ge=0, le=65535)
    green: Optional[int] = Field(default=None, ge=0, le=65535)
    blue: Optional[int] = Field(default=None, ge=0, le=65535)
    clear: Optional[int] = Field(default=None, ge=0, le=65535)
    optical_colour_index: float = Field(..., ge=0.0, le=1.0, allow_inf_nan=False)
    calibration_id: Optional[int] = None
    source: DataSource


class ForecastRequest(BaseModel):
    """Request for water quality forecast."""

    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    # Omitting readings is supported only in explicit development mode, where
    # the backend may select its stored SIMULATED_DEVELOPMENT history.
    readings: Optional[list[ForecastReading]] = Field(default=None, min_length=1, max_length=1000)
    # A request-level source is useful for selecting stored provenance without
    # requiring clients to resubmit the observations. It is checked against
    # every supplied observation and defaults by environment in the route.
    source: Optional[DataSource] = None

    @model_validator(mode="after")
    def timestamps_are_unique_and_ordered(self):
        if self.readings is None:
            return self
        parsed = [datetime.fromisoformat(reading.timestamp.replace("Z", "+00:00")) for reading in self.readings]
        if any(value.tzinfo is None for value in parsed):
            raise ValueError("Forecast timestamps must include a timezone.")
        normalized = [value.astimezone(timezone.utc) for value in parsed]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Forecast history contains duplicate timestamps.")
        if any(later <= earlier for earlier, later in zip(normalized, normalized[1:])):
            raise ValueError("Forecast readings must be in strictly chronological order.")
        if any(value > datetime.now(timezone.utc) for value in normalized):
            raise ValueError("Forecast history cannot contain future-dated observations.")
        return self


class ModelPrediction(BaseModel):
    """Prediction from a single model."""

    pH: float
    TDS: float
    turbidity: float
    temperature: float
    optical_colour_index: float


class ModelWeights(BaseModel):
    """Weights for a single parameter across models."""

    LSTM: float
    PatchTST: float
    TimeMixer: float


class ForecastResponse(BaseModel):
    """Response from forecast endpoint."""

    model_config = ConfigDict(extra="forbid")

    forecast_date: str
    prediction: ModelPrediction
    model_predictions: dict[str, ModelPrediction]
    weights: dict[str, ModelWeights]
    node_id: str
    input_start: str
    input_end: str
    data_source: str
    model_versions: dict[str, str]
    weight_strategy: Literal["initial", "adaptive"]
    weight_status: str
    forecast_horizon_hours: int = 24
