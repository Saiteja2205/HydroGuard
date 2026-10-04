"""Pydantic schemas for forecast-related API endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ModelPrediction(BaseModel):
    """Prediction from a single model."""

    pH: float
    TDS: float
    turbidity: float
    temperature: Optional[float] = None


class ModelWeights(BaseModel):
    """Weights for a single parameter across models."""

    LSTM: float
    PatchTST: float
    TimeMixer: float


class ForecastRecord(BaseModel):
    """Stored forecast record from database."""

    model_config = {"from_attributes": True, "extra": "forbid"}

    id: int
    node_id: str
    created_at: datetime
    forecast_date: datetime
    horizon_hours: int = 24
    input_start: Optional[datetime] = None
    input_end: Optional[datetime] = None
    data_source: str = "HISTORICAL_DATA"
    model_versions: Optional[dict[str, str]] = None
    weight_strategy: str = "initial"

    # LSTM predictions
    lstm_ph: float
    lstm_tds: float
    lstm_turbidity: float
    lstm_temperature: Optional[float] = None

    # PatchTST predictions
    patchtst_ph: float
    patchtst_tds: float
    patchtst_turbidity: float
    patchtst_temperature: Optional[float] = None

    # TimeMixer predictions
    timemixer_ph: float
    timemixer_tds: float
    timemixer_turbidity: float
    timemixer_temperature: Optional[float] = None

    # Ensemble predictions
    ensemble_ph: float
    ensemble_tds: float
    ensemble_turbidity: float
    ensemble_temperature: Optional[float] = None

    # Model weights for pH
    lstm_weight_ph: float
    patchtst_weight_ph: float
    timemixer_weight_ph: float

    # Model weights for TDS
    lstm_weight_tds: float
    patchtst_weight_tds: float
    timemixer_weight_tds: float

    # Model weights for turbidity
    lstm_weight_turbidity: float
    patchtst_weight_turbidity: float
    timemixer_weight_turbidity: float

    # Model weights for temperature
    lstm_weight_temperature: float
    patchtst_weight_temperature: float
    timemixer_weight_temperature: float

class ForecastListResponse(BaseModel):
    """Response for forecast list endpoint."""

    forecasts: list[ForecastRecord]
    count: int


class ModelPerformance(BaseModel):
    """Model performance metrics."""

    model_name: str
    parameter: str
    mae: float
    rmse: float
    count: int
    data_source: str
    horizon_hours: int = 24
    evaluation_start: Optional[datetime] = None
    evaluation_end: Optional[datetime] = None
    mape: Optional[float] = None


class ModelPerformanceResponse(BaseModel):
    """Response for model performance endpoint."""

    node_id: str
    performance: list[ModelPerformance]
