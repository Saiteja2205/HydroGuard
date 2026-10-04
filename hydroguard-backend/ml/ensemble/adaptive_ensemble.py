"""Adaptive Ensemble for HydroGuard water quality forecasting.

Combines predictions from LSTM, PatchTST, and TimeMixer using
adaptive inverse error weighting based on recent forecasting performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ml.ensemble.weighting import (
    WeightingConfig,
    calculate_error_score,
    calculate_parameter_weights,
    combine_predictions,
    get_average_errors,
    get_current_weights,
    update_error_history,
)


@dataclass
class AdaptiveEnsembleConfig:
    """Configuration for adaptive ensemble."""

    model_names: tuple[str, ...] = ("LSTM", "PatchTST", "TimeMixer")
    parameters: tuple[str, ...] = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")
    alpha: float = 0.5  # Weight for MAE in error score
    epsilon: float = 1e-8  # Small constant to prevent division by zero
    window_size: int = 30  # Rolling window size for error history
    min_weight: float = 0.05  # Minimum weight per model
    max_weight: float = 0.9  # Maximum weight per model


@dataclass
class EnsembleState:
    """State tracking for adaptive ensemble."""

    error_history: list[dict[str, dict[str, float]]] = field(default_factory=list)
    current_weights: dict[str, dict[str, float]] = field(default_factory=dict)
    last_predictions: dict[str, dict[str, float]] = field(default_factory=dict)
    last_errors: dict[str, dict[str, float]] = field(default_factory=dict)


class AdaptiveEnsemble:
    """Adaptive ensemble for combining model predictions.

    Dynamically updates model contribution weights based on recent
    forecasting errors using inverse error weighting.
    """

    def __init__(
        self,
        config: AdaptiveEnsembleConfig | None = None,
    ):
        self.config = config or AdaptiveEnsembleConfig()
        self.state = EnsembleState()

        # Initialize equal weights if no history
        self._initialize_equal_weights()

    def _initialize_equal_weights(self) -> None:
        """Initialize equal weights for all models and parameters."""
        equal_weight = 1.0 / len(self.config.model_names)
        for param in self.config.parameters:
            self.state.current_weights[param] = {
                model: equal_weight for model in self.config.model_names
            }

    def get_weighting_config(self) -> WeightingConfig:
        """Get weighting configuration."""
        return WeightingConfig(
            alpha=self.config.alpha,
            epsilon=self.config.epsilon,
            window_size=self.config.window_size,
            min_weight=self.config.min_weight,
            max_weight=self.config.max_weight,
        )

    def calculate_model_errors(
        self,
        predictions: dict[str, dict[str, float]],
        ground_truth: dict[str, float],
    ) -> dict[str, dict[str, float]]:
        """Calculate MAE and RMSE for each model and parameter.

        Args:
            predictions: Dictionary mapping model names to parameter predictions
            ground_truth: Dictionary of ground truth values per parameter

        Returns:
            Dictionary mapping model names to error dictionaries
                     with 'mae' and 'rmse' for each parameter
        """
        model_errors = {}

        for model_name in self.config.model_names:
            model_errors[model_name] = {}
            for param in self.config.parameters:
                pred = predictions[model_name][param]
                true = ground_truth[param]

                # Calculate MAE
                mae = abs(pred - true)

                # Calculate RMSE
                rmse = np.sqrt((pred - true) ** 2)

                model_errors[model_name][param] = {
                    "mae": mae,
                    "rmse": rmse,
                }

        return model_errors

    def calculate_error_scores(
        self,
        model_errors: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """Calculate combined error scores from MAE and RMSE.

        Args:
            model_errors: Dictionary with 'mae' and 'rmse' for each model/parameter

        Returns:
            Dictionary of error scores per model and parameter
        """
        error_scores = {}

        for model_name in self.config.model_names:
            error_scores[model_name] = {}
            for param in self.config.parameters:
                mae = model_errors[model_name][param]["mae"]
                rmse = model_errors[model_name][param]["rmse"]
                score = calculate_error_score(mae, rmse, self.config.alpha)
                error_scores[model_name][param] = score

        return error_scores

    def update_weights(
        self,
        model_errors: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """Update ensemble weights based on model errors.

        Args:
            model_errors: Dictionary of error scores per model and parameter

        Returns:
            Updated weights per parameter and model
        """
        weighting_config = self.get_weighting_config()
        new_weights = calculate_parameter_weights(model_errors, weighting_config)
        self.state.current_weights = new_weights
        return new_weights

    def update_history(
        self,
        model_errors: dict[str, dict[str, float]],
    ) -> None:
        """Update error history with current model errors.

        Args:
            model_errors: Dictionary of error scores per model and parameter
        """
        self.state.error_history = update_error_history(
            model_errors,
            self.state.error_history,
            self.config.window_size,
        )

    def update_from_predictions(
        self,
        predictions: dict[str, dict[str, float]],
        ground_truth: dict[str, float],
    ) -> dict[str, dict[str, float]]:
        """Update ensemble from new predictions and ground truth.

        Args:
            predictions: Dictionary of model predictions
            ground_truth: Dictionary of ground truth values

        Returns:
            Updated weights
        """
        # Calculate model errors
        model_errors = self.calculate_model_errors(predictions, ground_truth)

        # Calculate error scores
        error_scores = self.calculate_error_scores(model_errors)

        # Update error history
        self.update_history(error_scores)

        # Update weights based on average errors
        avg_errors = get_average_errors(self.state.error_history)
        self.state.current_weights = calculate_parameter_weights(avg_errors, self.get_weighting_config())

        # Store last predictions and errors
        self.state.last_predictions = predictions
        self.state.last_errors = error_scores

        return self.state.current_weights

    def combine(
        self,
        predictions: dict[str, dict[str, float]],
    ) -> dict[str, float]:
        """Combine model predictions using current weights.

        Args:
            predictions: Dictionary of model predictions per parameter

        Returns:
            Combined predictions per parameter
        """
        return combine_predictions(predictions, self.state.current_weights, self.config.parameters)

    def get_current_weights(self) -> dict[str, dict[str, float]]:
        """Get current ensemble weights.

        Returns:
            Dictionary of weights per parameter and model
        """
        return self.state.current_weights

    def get_state(self) -> EnsembleState:
        """Get current ensemble state.

        Returns:
            Current ensemble state
        """
        return self.state

    def reset_weights(self) -> None:
        """Reset weights to equal distribution."""
        self._initialize_equal_weights()
        self.state.error_history = []
        self.state.last_predictions = {}
        self.state.last_errors = {}

    def get_error_history_length(self) -> int:
        """Get current length of error history.

        Returns:
            Number of error entries in history
        """
        return len(self.state.error_history)

    def get_average_errors(self) -> dict[str, dict[str, float]]:
        """Get average errors over the history window.

        Returns:
            Dictionary of average errors per model and parameter
        """
        return get_average_errors(self.state.error_history)

    def get_summary(self) -> dict[str, Any]:
        """Get ensemble summary information.

        Returns:
            Dictionary with ensemble state summary
        """
        return {
            "model_names": self.config.model_names,
            "parameters": self.config.parameters,
            "window_size": self.config.window_size,
            "history_length": self.get_error_history_length(),
            "current_weights": self.state.current_weights,
            "average_errors": self.get_average_errors(),
            "last_errors": self.state.last_errors,
        }


def create_ensemble(
    config: AdaptiveEnsembleConfig | None = None,
) -> AdaptiveEnsemble:
    """Factory function to create an adaptive ensemble.

    Args:
        config: Ensemble configuration

    Returns:
        Initialized AdaptiveEnsemble instance
    """
    return AdaptiveEnsemble(config)


def combine_predictions_simple(
    predictions: dict[str, dict[str, float]],
    weights: dict[str, dict[str, float]],
    parameters: tuple[str, ...],
) -> dict[str, float]:
    """Simple combination function (exposed for external use).

    Args:
        predictions: Dictionary of model predictions
        weights: Dictionary of weights per parameter
        parameters: Parameter names

    Returns:
        Combined predictions
    """
    return combine_predictions(predictions, weights, parameters)
