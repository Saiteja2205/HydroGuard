"""Response schemas for the ThingSpeak-backed forecast endpoint.

The endpoint bridges three independently-trainable things: a live ThingSpeak
channel, the three cached PyTorch checkpoints, and the weighted ensemble. Each
of those has a different trust level, so the response keeps them apart rather
than flattening them into one number a client might over-trust.

The field the mobile app is most likely to over-trust is ``provenance``:

* ``data_source`` is the channel that supplied the *observations*.
* ``models_trained_on`` / ``real_sensor_data`` describe what the *weights*
  were fitted against. The shipped checkpoints were trained on a 200-row
  simulated development dataset, so a forecast computed from a real channel is
  still a development-trained model's extrapolation, not a certified
  measurement.

Those are separate facts on purpose. Reading real feeds does not retroactively
make the model weights real-sensor-trained, and collapsing the two would let a
caller believe a forecast is better validated than it is.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic import model_serializer


class ThingSpeakReadingValues(BaseModel):
    """The five modelled parameters for one observation, in physical units.

    Note: optical_colour_index is optional because it is not directly measured
    by the hardware. When unavailable, it will be None and excluded from serialization.
    """

    model_config = ConfigDict(extra="forbid")

    pH: float
    TDS: float
    turbidity: float
    temperature: float
    optical_colour_index: Optional[float] = None

    @model_serializer(mode="wrap")
    def serialize_model(self, handler):
        data = handler(self)
        # Exclude optical_colour_index when it's None to avoid misleading clients
        if data.get("optical_colour_index") is None:
            data.pop("optical_colour_index", None)
        return data


class ThingSpeakRGBValues(BaseModel):
    """Raw RGB sensor readings from the ThingSpeak channel (fields 5-7).

    These are NOT fed into the ML models. Values are 0–100 relative intensity
    percentages from the TCS34725 firmware and may be None if the channel
    does not log them. Field 8 is a status flag (0=normal, 1=abnormal);
    field 9 (clear) does not exist on this hardware.
    """

    model_config = ConfigDict(extra="forbid")

    red: Optional[int] = None
    green: Optional[int] = None
    blue: Optional[int] = None
    clear: Optional[int] = None


class ThingSpeakLatestReading(BaseModel):
    """The newest observation actually present in the fetched window.

    ``timestamp`` is None when no feed in the window carried a parseable
    timestamp. It is deliberately not defaulted to "now": a forecast whose
    observation time is unknown must say so rather than imply it is current.
    """

    model_config = ConfigDict(extra="forbid", exclude_none=True)

    timestamp: Optional[str] = None
    values: ThingSpeakReadingValues
    observed_at: Optional[str] = Field(
        default=None,
        description="Observation time of the newest feed, as reported by ThingSpeak.",
    )
    rgb: Optional[ThingSpeakRGBValues] = Field(
        default=None,
        description="Raw RGB sensor counts from the newest feed (if available).",
    )
    entry_id: Optional[int] = Field(
        default=None,
        description="ThingSpeak feed entry ID.",
    )
    status_flag: Optional[int] = Field(
        default=None,
        description="Hardware status flag from field8 (e.g. 0=normal, 1=abnormal).",
    )
    channel_id: Optional[str] = Field(
        default=None,
        description="ThingSpeak numeric channel identifier.",
    )
    node_id: Optional[str] = Field(
        default=None,
        description="Associated sensor node identifier (e.g. thingspeak-244357).",
    )



class ThingSpeakForecastBlock(BaseModel):
    """Per-model and ensemble forecasts for the next step, in physical units."""

    model_config = ConfigDict(extra="forbid")

    lstm: ThingSpeakReadingValues
    patchtst: ThingSpeakReadingValues
    timemixer: ThingSpeakReadingValues
    ensemble: ThingSpeakReadingValues


class WindowProvenance(BaseModel):
    """How much of the 30-row window was measured versus carried forward.

    ThingSpeak omits a field for any interval where the device did not log it,
    and a young channel may have fewer than 30 feeds at all. Those gaps are
    filled (causally, then by repeating the first reading) but never hidden:
    every fill is counted here so a caller can judge how much of the input was
    actually observed.
    """

    model_config = ConfigDict(extra="forbid")

    window_size: int = Field(..., description="Rows fed to the models.")
    observed_rows: int = Field(..., description="Rows that came from real channel feeds.")
    forward_filled: int = Field(
        ..., description="Cells carrying an earlier observed value (causal fill)."
    )
    leading_filled: int = Field(
        ..., description="Head cells repeating the field's first observed value."
    )
    padded_rows: int = Field(
        ..., description="Rows prepended because the channel had fewer feeds than the window."
    )
    missing_by_parameter: dict[str, int] = Field(
        default_factory=dict,
        description="Per-parameter count of absent cells before any fill.",
    )
    unobserved_parameters: list[str] = Field(
        default_factory=list,
        description="Parameters the channel never reported; filled with range midpoints.",
    )
    rgb_missing_by_channel: dict[str, int] = Field(
        default_factory=dict,
        description="Per-RGB-channel count of absent cells.",
    )
    source_rows_fetched: int = Field(
        default=0,
        description="Total raw feeds fetched from ThingSpeak before filtering or padding.",
    )
    observed_by_parameter: dict[str, int] = Field(
        default_factory=dict,
        description="Per-parameter count of genuinely observed valid sensor values.",
    )


class ForecastProvenance(BaseModel):
    """Trust metadata separating where observations came from from what the
    model weights were trained on. These are different facts and are kept
    different so a real channel cannot be mistaken for real-trained weights."""

    model_config = ConfigDict(extra="forbid")

    data_source: Literal["THINGSPEAK"] = "THINGSPEAK"
    channel_id: str
    models_trained_on: str = Field(
        ..., description="Checkpoint dataset_source, e.g. SIMULATED_DEVELOPMENT."
    )
    real_sensor_data: bool = Field(
        ..., description="Whether the checkpoints were fitted on real sensor rows."
    )
    window: WindowProvenance
    fetched_at: str = Field(..., description="Server time the channel was read, UTC ISO-8601.")


class ThingSpeakForecastResponse(BaseModel):
    """Success payload for ``GET /api/v1/thingspeak/forecast``.

    The shape keeps the requested keys (``latest_reading`` and ``forecast``)
    and adds ``provenance`` plus an explicit ``disclaimer`` so a mobile client
    cannot present an app-derived index as a certified drinking-water safety
    rating.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    latest_reading: ThingSpeakLatestReading
    forecast: ThingSpeakForecastBlock
    prediction: Optional[ThingSpeakReadingValues] = None
    weights: dict[str, dict[str, float]]
    model_versions: dict[str, str]
    provenance: ForecastProvenance
    forecast_horizon_hours: int = 24
    sample_interval_seconds: Optional[int] = Field(
        default=None,
        description='Observed interval in seconds between the latest two feeds (e.g. 30-45s).',
    )
    prediction_semantics: str = Field(
        default='next_step_experimental',
        description='Semantics of model prediction: next-step (t+1) extrapolation from models trained on 24-hour interval simulated data.',
    )
    forecast_horizon_description: str = Field(
        default='Next-step prediction (experimental; nominal 24h interval in training simulation)',
        description='Explicit description of the forecast horizon.',
    )
    target_timestamp: Optional[str] = Field(
        default=None,
        description='ISO-8601 UTC timestamp of the expected next observation based on live interval.',
    )
    disclaimer: str = Field(
        default=(
            "Development-trained forecast. These values are model extrapolations "
            "and are not a certified drinking-water safety rating."
        )
    )
    model_lifecycle_state: str = Field(
        default="EXPERIMENTAL",
        description="Current lifecycle state of forecasting model: EXPERIMENTAL, VALIDATED, DEPLOYED, or REJECTED.",
    )
    next_day_forecast_status: str = Field(
        default="UNAVAILABLE_INSUFFICIENT_REAL_DATA",
        description="Status of genuine next-day (24h) forecast: UNAVAILABLE_INSUFFICIENT_REAL_DATA, EXPERIMENTAL, or VALIDATED.",
    )
    next_day_forecast_reason: str = Field(
        default="Real sensor data coverage is 0.68% (71 minutes active operation across 7 days with multi-hour gaps). Zero continuous 24-hour windows exist to train or validate genuine next-day forecasting. An experimental next-step (~33s) prediction is provided as a baseline.",
        description="Scientifically grounded explanation of next-day forecast status.",
    )
    data_coverage_percent: float = Field(
        default=0.684,
        description="Temporal coverage percentage of real sensor stream over calendar span.",
    )
    continuous_24h_windows: int = Field(
        default=0,
        description="Number of continuous 24-hour windows available in real sensor stream meeting quality threshold.",
    )


class ThingSpeakForecastUnavailable(BaseModel):
    """Returned when the forecast cannot be generated because optical_colour_index
    is not available from the sensor hardware."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["forecast_unavailable"] = "forecast_unavailable"
    detail: str
    latest_reading: ThingSpeakLatestReading
    provenance: ForecastProvenance


ThingSpeakForecastResponseUnion = ThingSpeakForecastResponse | ThingSpeakForecastUnavailable


class ThingSpeakForecastNotConfigured(BaseModel):
    """Returned when no channel is configured, so the failure is explicit."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_configured"] = "not_configured"
    detail: str


class ThingSpeakHistoryReading(BaseModel):
    """One historical reading entry from the ThingSpeak feed."""

    model_config = ConfigDict(extra="ignore")

    timestamp: Optional[str] = None
    entry_id: Optional[int] = None
    ph: Optional[float] = None
    pH: Optional[float] = None
    tds: Optional[float] = None
    TDS: Optional[float] = None
    turbidity: Optional[float] = None
    temperature: Optional[float] = None
    red: Optional[int] = None
    green: Optional[int] = None
    blue: Optional[int] = None
    status_flag: Optional[int] = None
    source: str = "THINGSPEAK"



class ThingSpeakHistoryResponse(BaseModel):
    """Chronologically ordered historical feed readings from ThingSpeak."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str
    count: int
    source: str = "THINGSPEAK"
    readings: list[ThingSpeakHistoryReading]
