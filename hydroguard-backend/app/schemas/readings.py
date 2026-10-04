from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

DataSource = Literal["REAL_SENSOR", "HISTORICAL_DATA", "DEMO", "SIMULATED"]
PRODUCT_PARAMETERS = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")


class ModelsLoadedStatus(BaseModel):
    lstm: bool = False
    patchtst: bool = False
    timemixer: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    sensors_connected: bool
    models_loaded: ModelsLoadedStatus
    data_mode: Literal["historical_or_simulated"]


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
        return {"esp32": "REAL_SENSOR", "manual": "HISTORICAL_DATA", "historical_demo": "DEMO", "simulated": "SIMULATED"}.get(str(value).lower(), str(value).upper())

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Reading timestamp must include a timezone.")
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
        return {"esp32": "REAL_SENSOR", "manual": "HISTORICAL_DATA", "historical_demo": "DEMO", "simulated": "SIMULATED"}.get(str(value).lower(), str(value).upper())

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("created_at")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
    readings: list[ForecastReading] = Field(..., min_length=1, max_length=1000)

    @model_validator(mode="after")
    def timestamps_are_unique_and_ordered(self):
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
