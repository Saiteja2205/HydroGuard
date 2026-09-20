from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer


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
    """Development reading. EC and DO are nullable until those sensors exist."""

    node_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    timestamp: datetime
    ph: float = Field(..., ge=0.0, le=14.0)
    tds: float = Field(..., ge=0.0)
    turbidity: float = Field(..., ge=0.0)
    temperature: float = Field(..., ge=-20.0, le=80.0)
    ec: Optional[float] = Field(default=None, ge=0.0)
    do: Optional[float] = Field(default=None, ge=0.0)
    flow_rate: float = Field(..., ge=0.0)
    source: Literal["historical_or_simulated"]

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ForecastReading(BaseModel):
    """Single water quality reading for forecast input."""

    timestamp: str
    pH: float = Field(..., ge=0.0, le=14.0)
    TDS: float = Field(..., ge=0.0)
    turbidity: float = Field(..., ge=0.0)
    temperature: float = Field(..., ge=-20.0, le=80.0)
    EC: Optional[float] = Field(default=None, ge=0.0)
    DO: Optional[float] = Field(default=None, ge=0.0)


class ForecastRequest(BaseModel):
    """Request for water quality forecast."""

    readings: list[ForecastReading] = Field(..., min_length=30, max_length=30)
    four_parameter_mode: bool = False  # If True, EC/DO are not required

    def validate_six_parameter_mode(self) -> None:
        """Validate that EC and DO are present in six-parameter mode."""
        if self.four_parameter_mode:
            # Skip validation for four-parameter mode
            return
        
        has_ec = any(reading.EC is not None for reading in self.readings)
        has_do = any(reading.DO is not None for reading in self.readings)
        
        if not has_ec or not has_do:
            raise ValueError(
                "Forecast requires valid EC and DO measurements for six-parameter mode. "
                "No fabricated values will be used."
            )


class ModelPrediction(BaseModel):
    """Prediction from a single model."""

    pH: float
    TDS: float
    turbidity: float
    temperature: float
    EC: Optional[float] = None
    DO: Optional[float] = None


class ModelWeights(BaseModel):
    """Weights for a single parameter across models."""

    LSTM: float
    PatchTST: float
    TimeMixer: float


class ForecastResponse(BaseModel):
    """Response from forecast endpoint."""

    forecast_date: str
    prediction: ModelPrediction
    model_predictions: dict[str, ModelPrediction]
    weights: dict[str, ModelWeights]
