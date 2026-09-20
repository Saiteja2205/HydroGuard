"""Inference helpers for HydroGuard forecasting models."""

from ml.prediction.predict_lstm import (
    calculate_metrics,
    evaluate_on_test,
    load_model_for_prediction,
    predict,
    predict_with_inverse_transform,
)
from ml.prediction.predict_patchtst import (
    calculate_metrics as patchtst_calculate_metrics,
    evaluate_on_test as patchtst_evaluate_on_test,
    load_model_for_prediction as patchtst_load_model_for_prediction,
    predict as patchtst_predict,
    predict_as_dict,
    predict_with_inverse_transform as patchtst_predict_with_inverse_transform,
)
from ml.prediction.predict_timemixer import (
    calculate_metrics as timemixer_calculate_metrics,
    evaluate_on_test as timemixer_evaluate_on_test,
    load_model_for_prediction as timemixer_load_model_for_prediction,
    predict as timemixer_predict,
    predict_as_dict as timemixer_predict_as_dict,
    predict_with_inverse_transform as timemixer_predict_with_inverse_transform,
)

__all__ = [
    "calculate_metrics",
    "evaluate_on_test",
    "load_model_for_prediction",
    "predict",
    "predict_with_inverse_transform",
    "patchtst_calculate_metrics",
    "patchtst_evaluate_on_test",
    "patchtst_load_model_for_prediction",
    "patchtst_predict",
    "patchtst_predict_with_inverse_transform",
    "predict_as_dict",
    "timemixer_calculate_metrics",
    "timemixer_evaluate_on_test",
    "timemixer_load_model_for_prediction",
    "timemixer_predict",
    "timemixer_predict_with_inverse_transform",
    "timemixer_predict_as_dict",
]
