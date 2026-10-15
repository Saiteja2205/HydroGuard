"""Forecast service module for HydroGuard.

Provides orchestration layer for complete forecasting workflow.
"""

from ml.services.forecast_service import (
    ForecastService,
    ForecastServiceConfig,
    create_forecast_service,
)
from ml.services.thingspeak_service import (
    ThingSpeakConfig,
    ThingSpeakError,
    ThingSpeakInvalidChannel,
    ThingSpeakNotConfigured,
    ThingSpeakUnavailable,
    ThingSpeakWindow,
    fetch_feeds,
    fetch_window,
    load_config_from_env,
    parse_feeds,
)
from ml.services.inference_service import (
    CheckpointIncompatible,
    CheckpointMissing,
    InferenceError,
    InferenceResult,
    InferenceService,
    get_inference_service,
    reset_inference_service,
)

__all__ = [
    "CheckpointIncompatible",
    "CheckpointMissing",
    "ForecastService",
    "ForecastServiceConfig",
    "InferenceError",
    "InferenceResult",
    "InferenceService",
    "ThingSpeakConfig",
    "ThingSpeakError",
    "ThingSpeakInvalidChannel",
    "ThingSpeakNotConfigured",
    "ThingSpeakUnavailable",
    "ThingSpeakWindow",
    "create_forecast_service",
    "fetch_feeds",
    "fetch_window",
    "get_inference_service",
    "load_config_from_env",
    "parse_feeds",
    "reset_inference_service",
]
