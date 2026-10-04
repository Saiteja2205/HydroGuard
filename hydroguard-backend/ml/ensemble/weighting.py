"""Weight calculation module for adaptive ensemble.

Implements inverse error weighting for combining predictions from multiple models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, log
from typing import Any

import numpy as np


@dataclass
class WeightingConfig:
    """Configuration for adaptive ensemble weighting."""

    alpha: float = 0.5  # Weight for MAE in error score (1-alpha for RMSE)
    epsilon: float = 1e-8  # Small constant to prevent division by zero
    window_size: int = 30  # Rolling window size for error history
    min_weight: float = 0.05  # Minimum weight per model
    max_weight: float = 0.9  # Maximum weight per model


def calculate_error_score(
    mae: float,
    rmse: float,
    alpha: float = 0.5,
) -> float:
    """Calculate combined error score from MAE and RMSE.

    Args:
        mae: Mean Absolute Error
        rmse: Root Mean Square Error
        alpha: Weight for MAE (0-1), (1-alpha) for RMSE

    Returns:
        Combined error score
    """
    return alpha * mae + (1 - alpha) * rmse


def calculate_weights(
    error_scores: list[float],
    config: WeightingConfig | None = None,
) -> list[float]:
    """Calculate inverse error weights from error scores.

    Lower error gets higher weight using inverse error weighting.

    Args:
        error_scores: List of error scores for each model
        config: Weighting configuration

    Returns:
        Normalized weights that sum to 1
    """
    config = config or WeightingConfig()

    if not error_scores:
        raise ValueError("At least one model error score is required.")
    if not 0.0 <= config.min_weight <= config.max_weight <= 1.0:
        raise ValueError("Weight bounds must satisfy 0 <= min_weight <= max_weight <= 1.")
    if config.min_weight * len(error_scores) > 1.0:
        raise ValueError("Minimum weight is infeasible for the number of models.")
    if any(not isfinite(float(score)) or float(score) < 0 for score in error_scores):
        raise ValueError("Model error scores must be finite and non-negative.")

    # Normalize errors first to avoid overflow for tiny errors and underflow
    # for very large values, then project weights onto configured bounds.
    errors = np.asarray(error_scores, dtype=np.float64)
    if np.all(errors == 0):
        raw = np.full(len(errors), 1.0 / len(errors))
    else:
        scale = float(errors.min()) if float(errors.min()) > 0 else float(errors[errors > 0].min())
        # Work in log space to keep ratios finite even when error magnitudes
        # span the full float64 range. Values beyond 1/epsilon are equivalent
        # for the bounded weight projection and can safely be capped.
        log_ratios = np.full(errors.shape, -np.inf, dtype=np.float64)
        positive = errors > 0
        log_ratios[positive] = np.log(errors[positive]) - log(scale)
        max_log_ratio = log(1.0 / config.epsilon)
        ratios = np.exp(np.minimum(log_ratios, max_log_ratio))
        inverse = 1.0 / (ratios + config.epsilon)
        raw = inverse / inverse.sum()

    weights = raw.copy()
    for _ in range(len(weights) * 4):
        below = weights < config.min_weight
        above = weights > config.max_weight
        if not below.any() and not above.any():
            break
        fixed = below | above
        weights[below] = config.min_weight
        weights[above] = config.max_weight
        remaining = 1.0 - float(weights[fixed].sum())
        free = ~fixed
        if not free.any():
            break
        free_sum = float(raw[free].sum())
        weights[free] = remaining / free.sum() if free_sum == 0 else raw[free] * remaining / free_sum
    weights /= weights.sum()
    return weights.tolist()


def calculate_parameter_weights(
    model_errors: dict[str, dict[str, float]],
    config: WeightingConfig | None = None,
) -> dict[str, dict[str, float]]:
    """Calculate weights separately for each parameter.

    Args:
        model_errors: Dictionary mapping model names to parameter error dictionaries
                     e.g., {"LSTM": {"pH": 0.1, "TDS": 0.2}, ...}
        config: Weighting configuration

    Returns:
        Dictionary mapping model names to parameter weight dictionaries
    """
    config = config or WeightingConfig()

    # Get parameter names from first model
    first_model = next(iter(model_errors.values()))
    parameters = list(first_model.keys())

    # Calculate weights for each parameter separately
    parameter_weights = {}

    for param in parameters:
        # Collect error scores for this parameter across all models
        error_scores = [model_errors[model][param] for model in model_errors.keys()]

        # Calculate weights
        weights = calculate_weights(error_scores, config)

        # Assign weights to models
        param_weights = {}
        for i, model_name in enumerate(model_errors.keys()):
            param_weights[model_name] = weights[i]

        parameter_weights[param] = param_weights

    return parameter_weights


def update_error_history(
    current_errors: dict[str, dict[str, float]],
    error_history: list[dict[str, dict[str, float]]],
    window_size: int = 30,
) -> list[dict[str, dict[str, float]]]:
    """Update rolling error history with current errors.

    Args:
        current_errors: Current error scores for each model and parameter
        error_history: Existing error history
        window_size: Maximum number of error entries to keep

    Returns:
        Updated error history (truncated to window_size)
    """
    # Add current errors to history
    error_history.append(current_errors)

    # Truncate to window size
    if len(error_history) > window_size:
        error_history = error_history[-window_size:]

    return error_history


def get_average_errors(
    error_history: list[dict[str, dict[str, float]]],
) -> dict[str, dict[str, float]]:
    """Calculate average errors over the history window.

    Args:
        error_history: List of error dictionaries

    Returns:
        Dictionary of average errors per model and parameter
    """
    if not error_history:
        return {}

    # Get model names and parameters
    first_entry = error_history[0]
    model_names = list(first_entry.keys())
    parameters = list(first_entry[model_names[0]].keys())

    # Initialize average errors
    avg_errors = {
        model: {param: 0.0 for param in parameters}
        for model in model_names
    }

    # Sum errors across history
    for entry in error_history:
        for model in model_names:
            for param in parameters:
                avg_errors[model][param] += entry[model][param]

    # Divide by history length
    history_length = len(error_history)
    for model in model_names:
        for param in parameters:
            avg_errors[model][param] /= history_length

    return avg_errors


def combine_predictions(
    predictions: dict[str, np.ndarray],
    weights: dict[str, dict[str, float]],
    parameters: tuple[str, ...],
) -> dict[str, float]:
    """Combine model predictions using calculated weights.

    Args:
        predictions: Dictionary mapping model names to prediction arrays
        weights: Dictionary mapping parameter names to model weight dictionaries
        parameters: Tuple of parameter names

    Returns:
        Dictionary of weighted predictions per parameter
    """
    model_names = list(predictions.keys())

    # Initialize combined predictions
    combined = {param: 0.0 for param in parameters}

    # Weighted sum of predictions
    for param in parameters:
        param_total = 0.0
        for model in model_names:
            model_pred = predictions[model][param]  # Get prediction for this parameter
            model_weight = weights[param][model]  # Get weight for this model/parameter
            param_total += model_pred * model_weight
        combined[param] = param_total

    return combined


def get_current_weights(
    error_history: list[dict[str, dict[str, float]]],
    config: WeightingConfig | None = None,
) -> dict[str, dict[str, float]]:
    """Calculate current weights based on error history.

    Args:
        error_history: List of error dictionaries
        config: Weighting configuration

    Returns:
        Dictionary of current weights per parameter and model
    """
    config = config or WeightingConfig()

    # Calculate average errors over history
    avg_errors = get_average_errors(error_history)

    if not avg_errors:
        # No history yet, return equal weights for all parameters
        model_names = ("LSTM", "PatchTST", "TimeMixer")
        parameters = ("pH", "TDS", "turbidity", "temperature")
        equal_weight = 1.0 / len(model_names)
        return {
            param: {model: equal_weight for model in model_names}
            for param in parameters
        }

    # Calculate weights from average errors
    weights = calculate_parameter_weights(avg_errors, config)

    return weights
