"""Forecast service module for HydroGuard.

Provides orchestration layer for complete forecasting workflow.
"""

from ml.services.forecast_service import (
    ForecastService,
    ForecastServiceConfig,
    create_forecast_service,
)

__all__ = [
    "ForecastService",
    "ForecastServiceConfig",
    "create_forecast_service",
]
