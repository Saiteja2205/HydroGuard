"""Adaptive ensemble module for HydroGuard forecasting.

Combines predictions from LSTM, PatchTST, and TimeMixer using
adaptive inverse error weighting based on recent forecasting performance.
"""

from ml.ensemble.adaptive_ensemble import (
    AdaptiveEnsemble,
    AdaptiveEnsembleConfig,
    EnsembleState,
    combine_predictions_simple,
    create_ensemble,
)
from ml.ensemble.weighting import (
    WeightingConfig,
    calculate_error_score,
    calculate_parameter_weights,
    calculate_weights,
    combine_predictions,
    get_average_errors,
    get_current_weights,
    update_error_history,
)

__all__ = [
    "AdaptiveEnsemble",
    "AdaptiveEnsembleConfig",
    "EnsembleState",
    "combine_predictions_simple",
    "create_ensemble",
    "WeightingConfig",
    "calculate_error_score",
    "calculate_parameter_weights",
    "calculate_weights",
    "combine_predictions",
    "get_average_errors",
    "get_current_weights",
    "update_error_history",
]
