"""Shared HydroGuard ML data pipeline.

This package prepares historical or simulated CSV series for later forecasting
models. It does not load live sensors, invent EC/DO measurements, or train
LSTM / PatchTST / TimeMixer models.

Default forecasting setup:
    WINDOW_SIZE previous daily rows → the next day's parameter vector.
"""

from ml.data.dataset import (
    PARAMETERS,
    WINDOW_SIZE,
    PipelineConfig,
    PipelineResult,
    run_pipeline,
)
from ml.data.loader import load_csv
from ml.data.preprocessing import FeatureScaler, chronological_split
from ml.data.validator import REQUIRED_COLUMNS, ValidationReport, validate_raw_frame
from ml.data.window_generator import create_sliding_windows

__all__ = [
    "PARAMETERS",
    "REQUIRED_COLUMNS",
    "WINDOW_SIZE",
    "FeatureScaler",
    "PipelineConfig",
    "PipelineResult",
    "ValidationReport",
    "chronological_split",
    "create_sliding_windows",
    "load_csv",
    "run_pipeline",
    "validate_raw_frame",
]
