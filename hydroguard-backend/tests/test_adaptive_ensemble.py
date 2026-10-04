"""Unit tests for Adaptive Ensemble module.

Tests cover weight calculation, error handling, and prediction combination.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

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
from ml.ensemble.adaptive_ensemble import (
    AdaptiveEnsemble,
    AdaptiveEnsembleConfig,
    create_ensemble,
)


class ErrorScoreTests(unittest.TestCase):
    def test_error_score_calculation(self) -> None:
        """Test combined error score from MAE and RMSE."""
        mae = 0.5
        rmse = 0.7
        alpha = 0.5
        score = calculate_error_score(mae, rmse, alpha)
        expected = 0.5 * 0.5 + 0.5 * 0.7  # 0.6
        self.assertAlmostEqual(score, expected, places=6)

    def test_error_score_alpha_extremes(self) -> None:
        """Test error score with alpha = 0 and alpha = 1."""
        mae = 0.5
        rmse = 0.7

        # alpha = 0 (only RMSE)
        score_0 = calculate_error_score(mae, rmse, alpha=0.0)
        self.assertAlmostEqual(score_0, rmse, places=6)

        # alpha = 1 (only MAE)
        score_1 = calculate_error_score(mae, rmse, alpha=1.0)
        self.assertAlmostEqual(score_1, mae, places=6)


class WeightCalculationTests(unittest.TestCase):
    def test_weight_normalization(self) -> None:
        """Test that weights sum to 1."""
        error_scores = [0.1, 0.2, 0.3]
        weights = calculate_weights(error_scores)
        total = sum(weights)
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_inverse_error_weighting(self) -> None:
        """Test that lower error gets higher weight."""
        error_scores = [0.1, 0.2, 0.3]
        weights = calculate_weights(error_scores)

        # Lowest error (0.1) should get highest weight
        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[0], weights[2])

        # Highest error (0.3) should get lowest weight
        self.assertLess(weights[2], weights[0])
        self.assertLess(weights[2], weights[1])

    def test_equal_errors_equal_weights(self) -> None:
        """Test that equal errors produce equal weights."""
        error_scores = [0.2, 0.2, 0.2]
        weights = calculate_weights(error_scores)

        for i in range(len(weights) - 1):
            self.assertAlmostEqual(weights[i], weights[i + 1], places=6)

    def test_zero_error_handling(self) -> None:
        """Test handling of zero error scores."""
        error_scores = [0.0, 0.1, 0.2]
        config = WeightingConfig(epsilon=1e-8)
        weights = calculate_weights(error_scores, config)

        # Zero error should get highest weight
        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[0], weights[2])

        # Weights should still sum to 1
        self.assertAlmostEqual(sum(weights), 1.0, places=6)

    def test_min_max_weight_constraints(self) -> None:
        """Test min and max weight constraints."""
        error_scores = [0.001, 0.1, 1.0]  # Very different errors
        config = WeightingConfig(min_weight=0.1, max_weight=0.8)
        weights = calculate_weights(error_scores, config)

        # Check min constraint
        for w in weights:
            self.assertGreaterEqual(w, config.min_weight)

        # Check max constraint
        for w in weights:
            self.assertLessEqual(w, config.max_weight)

        # Weights should still sum to 1
        self.assertAlmostEqual(sum(weights), 1.0, places=6)


class ParameterWiseWeightsTests(unittest.TestCase):
    def test_parameter_wise_weight_calculation(self) -> None:
        """Test that weights are calculated separately for each parameter."""
        model_errors = {
            "LSTM": {"pH": 0.1, "TDS": 0.2, "temperature": 0.15, "turbidity": 0.12},
            "PatchTST": {"pH": 0.15, "TDS": 0.1, "temperature": 0.2, "turbidity": 0.14},
            "TimeMixer": {"pH": 0.2, "TDS": 0.15, "temperature": 0.1, "turbidity": 0.16},
        }

        weights = calculate_parameter_weights(model_errors)

        # Check that we have weights for each parameter
        self.assertIn("pH", weights)
        self.assertIn("TDS", weights)
        self.assertIn("temperature", weights)

        # Check that weights sum to 1 for each parameter
        for param in weights:
            param_total = sum(weights[param].values())
            self.assertAlmostEqual(param_total, 1.0, places=6)

    def test_different_weights_per_parameter(self) -> None:
        """Test that different parameters can have different weight distributions."""
        model_errors = {
            "LSTM": {"pH": 0.1, "TDS": 0.3, "temperature": 0.15, "turbidity": 0.12},
            "PatchTST": {"pH": 0.3, "TDS": 0.1, "temperature": 0.2, "turbidity": 0.14},
        }

        weights = calculate_parameter_weights(model_errors)

        # pH: LSTM should have higher weight (lower error)
        self.assertGreater(weights["pH"]["LSTM"], weights["pH"]["PatchTST"])

        # TDS: PatchTST should have higher weight (lower error)
        self.assertGreater(weights["TDS"]["PatchTST"], weights["TDS"]["LSTM"])


class ErrorHistoryTests(unittest.TestCase):
    def test_error_history_update(self) -> None:
        """Test updating error history."""
        current_errors = {
            "LSTM": {"pH": 0.1, "TDS": 0.2, "temperature": 0.15, "turbidity": 0.12},
            "PatchTST": {"pH": 0.15, "TDS": 0.1, "temperature": 0.2, "turbidity": 0.14},
        }
        history = []

        updated = update_error_history(current_errors, history, window_size=30)

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0], current_errors)

    def test_rolling_window_truncation(self) -> None:
        """Test that history is truncated to window size."""
        current_errors = {
            "LSTM": {"pH": 0.1, "TDS": 0.2},
            "PatchTST": {"pH": 0.15, "TDS": 0.1},
        }

        # Create history longer than window
        history = [current_errors.copy() for _ in range(35)]
        window_size = 30

        updated = update_error_history(current_errors, history, window_size)

        self.assertEqual(len(updated), window_size)

    def test_average_errors_calculation(self) -> None:
        """Test calculation of average errors over history."""
        error1 = {
            "LSTM": {"pH": 0.1, "TDS": 0.2, "temperature": 0.15, "turbidity": 0.12},
            "PatchTST": {"pH": 0.15, "TDS": 0.1, "temperature": 0.2, "turbidity": 0.14},
            "TimeMixer": {"pH": 0.2, "TDS": 0.15, "temperature": 0.1, "turbidity": 0.16},
        }
        error2 = {
            "LSTM": {"pH": 0.12, "TDS": 0.18, "temperature": 0.14, "turbidity": 0.13},
            "PatchTST": {"pH": 0.14, "TDS": 0.12, "temperature": 0.18, "turbidity": 0.15},
            "TimeMixer": {"pH": 0.18, "TDS": 0.16, "temperature": 0.12, "turbidity": 0.17},
        }

        history = [error1, error2]
        avg_errors = get_average_errors(history)

        # LSTM pH average: (0.1 + 0.12) / 2 = 0.11
        self.assertAlmostEqual(avg_errors["LSTM"]["pH"], 0.11, places=6)
        # PatchTST TDS average: (0.1 + 0.12) / 2 = 0.11
        self.assertAlmostEqual(avg_errors["PatchTST"]["TDS"], 0.11, places=6)

    def test_empty_history_handling(self) -> None:
        """Test handling of empty error history."""
        history = []
        avg_errors = get_average_errors(history)
        self.assertEqual(avg_errors, {})


class PredictionCombinationTests(unittest.TestCase):
    def test_weighted_prediction_combination(self) -> None:
        """Test combining predictions with weights."""
        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }

        weights = {
            "pH": {"LSTM": 0.5, "PatchTST": 0.3, "TimeMixer": 0.2},
            "TDS": {"LSTM": 0.3, "PatchTST": 0.5, "TimeMixer": 0.2},
            "turbidity": {"LSTM": 0.4, "PatchTST": 0.3, "TimeMixer": 0.3},
            "temperature": {"LSTM": 0.3, "PatchTST": 0.4, "TimeMixer": 0.3},
        }

        parameters = ("pH", "TDS", "turbidity", "temperature")
        combined = combine_predictions(predictions, weights, parameters)

        # pH: 7.0*0.5 + 7.2*0.3 + 7.1*0.2 = 3.5 + 2.16 + 1.42 = 7.08
        expected_pH = 7.0 * 0.5 + 7.2 * 0.3 + 7.1 * 0.2
        self.assertAlmostEqual(combined["pH"], expected_pH, places=6)

        # TDS: 180*0.3 + 182*0.5 + 181*0.2 = 54 + 91 + 36.2 = 181.2
        expected_TDS = 180.0 * 0.3 + 182.0 * 0.5 + 181.0 * 0.2
        self.assertAlmostEqual(combined["TDS"], expected_TDS, places=6)

    def test_missing_model_handling(self) -> None:
        """Test handling when a model is missing from predictions."""
        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            # TimeMixer missing
        }

        weights = {
            "pH": {"LSTM": 0.5, "PatchTST": 0.5, "TimeMixer": 0.0},
            "TDS": {"LSTM": 0.5, "PatchTST": 0.5, "TimeMixer": 0.0},
            "turbidity": {"LSTM": 0.5, "PatchTST": 0.5, "TimeMixer": 0.0},
            "temperature": {"LSTM": 0.5, "PatchTST": 0.5, "TimeMixer": 0.0},
        }

        parameters = ("pH", "TDS", "turbidity", "temperature")
        combined = combine_predictions(predictions, weights, parameters)

        # Should only use available models
        expected_pH = 7.0 * 0.5 + 7.2 * 0.5
        self.assertAlmostEqual(combined["pH"], expected_pH, places=6)


class AdaptiveEnsembleTests(unittest.TestCase):
    def test_ensemble_initialization(self) -> None:
        """Test ensemble initialization with equal weights."""
        ensemble = create_ensemble()
        weights = ensemble.get_current_weights()

        # Check that all parameters have weights
        for param in ensemble.config.parameters:
            self.assertIn(param, weights)

        # Check that weights sum to 1 for each parameter
        for param in weights:
            param_total = sum(weights[param].values())
            self.assertAlmostEqual(param_total, 1.0, places=6)

    def test_ensemble_custom_config(self) -> None:
        """Test ensemble with custom configuration."""
        config = AdaptiveEnsembleConfig(
            alpha=0.7,
            window_size=14,
            min_weight=0.1,
            max_weight=0.8,
        )
        ensemble = create_ensemble(config)

        self.assertEqual(ensemble.config.alpha, 0.7)
        self.assertEqual(ensemble.config.window_size, 14)
        self.assertEqual(ensemble.config.min_weight, 0.1)
        self.assertEqual(ensemble.config.max_weight, 0.8)

    def test_ensemble_update_from_predictions(self) -> None:
        """Test updating ensemble from predictions and ground truth."""
        ensemble = create_ensemble()

        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }

        ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}

        weights = ensemble.update_from_predictions(predictions, ground_truth)

        # Check that weights were updated
        self.assertIn("pH", weights)
        self.assertIn("TDS", weights)

        # Check that weights sum to 1
        for param in weights:
            param_total = sum(weights[param].values())
            self.assertAlmostEqual(param_total, 1.0, places=6)

    def test_ensemble_combine_predictions(self) -> None:
        """Test combining predictions through ensemble."""
        ensemble = create_ensemble()

        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }

        combined = ensemble.combine(predictions)

        # Check that all parameters are in output
        for param in ensemble.config.parameters:
            self.assertIn(param, combined)

    def test_ensemble_weight_adaptation(self) -> None:
        """Test that weights adapt based on model performance."""
        ensemble = create_ensemble(AdaptiveEnsembleConfig(window_size=5))

        # First update: LSTM performs better on pH
        predictions1 = {
            "LSTM": {"pH": 7.05, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.3, "TDS": 181.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth1 = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}
        ensemble.update_from_predictions(predictions1, ground_truth1)

        # Second update: LSTM still performs better on pH
        predictions2 = {
            "LSTM": {"pH": 7.08, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.25, "TDS": 181.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.18, "TDS": 182.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth2 = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}
        ensemble.update_from_predictions(predictions2, ground_truth2)

        weights = ensemble.get_current_weights()

        # LSTM should have higher weight for pH (better performance)
        self.assertGreater(weights["pH"]["LSTM"], weights["pH"]["PatchTST"])
        self.assertGreater(weights["pH"]["LSTM"], weights["pH"]["TimeMixer"])

    def test_ensemble_reset_weights(self) -> None:
        """Test resetting weights to equal distribution."""
        ensemble = create_ensemble()

        # Update with some predictions to change weights
        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}
        ensemble.update_from_predictions(predictions, ground_truth)

        # Reset weights
        ensemble.reset_weights()
        weights = ensemble.get_current_weights()

        # Check that weights are equal
        for param in weights:
            weights_list = list(weights[param].values())
            for i in range(len(weights_list) - 1):
                self.assertAlmostEqual(weights_list[i], weights_list[i + 1], places=6)

    def test_ensemble_error_history_tracking(self) -> None:
        """Test that error history is tracked correctly."""
        ensemble = create_ensemble(AdaptiveEnsembleConfig(window_size=10))

        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}

        # Update multiple times
        for _ in range(5):
            ensemble.update_from_predictions(predictions, ground_truth)

        history_length = ensemble.get_error_history_length()
        self.assertEqual(history_length, 5)

    def test_ensemble_rolling_window(self) -> None:
        """Test that rolling window truncates old errors."""
        ensemble = create_ensemble(AdaptiveEnsembleConfig(window_size=3))

        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}

        # Update more times than window size
        for _ in range(10):
            ensemble.update_from_predictions(predictions, ground_truth)

        history_length = ensemble.get_error_history_length()
        self.assertEqual(history_length, 3)

    def test_ensemble_get_average_errors(self) -> None:
        """Test getting average errors from history."""
        ensemble = create_ensemble(AdaptiveEnsembleConfig(window_size=10))

        predictions = {
            "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.5},
            "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.5},
            "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5},
        }
        ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.5}

        # Update multiple times
        for _ in range(5):
            ensemble.update_from_predictions(predictions, ground_truth)

        avg_errors = ensemble.get_average_errors()

        # Check that average errors are calculated
        self.assertIn("LSTM", avg_errors)
        self.assertIn("PatchTST", avg_errors)
        self.assertIn("TimeMixer", avg_errors)

        # Check that parameters are present
        for model in avg_errors:
            self.assertIn("pH", avg_errors[model])
            self.assertIn("TDS", avg_errors[model])

    def test_ensemble_get_summary(self) -> None:
        """Test getting ensemble summary."""
        ensemble = create_ensemble()
        summary = ensemble.get_summary()

        # Check summary contains expected keys
        self.assertIn("model_names", summary)
        self.assertIn("parameters", summary)
        self.assertIn("window_size", summary)
        self.assertIn("history_length", summary)
        self.assertIn("current_weights", summary)
        self.assertIn("average_errors", summary)

        # Check that model names are correct
        self.assertEqual(summary["model_names"], ("LSTM", "PatchTST", "TimeMixer"))


class CurrentWeightsTests(unittest.TestCase):
    def test_get_current_weights_from_history(self) -> None:
        """Test getting current weights from error history."""
        error_history = [
            {
                "LSTM": {"pH": 0.1, "TDS": 0.2, "temperature": 0.15, "turbidity": 0.12},
                "PatchTST": {"pH": 0.15, "TDS": 0.1, "temperature": 0.2, "turbidity": 0.14},
                "TimeMixer": {"pH": 0.2, "TDS": 0.15, "temperature": 0.1, "turbidity": 0.16},
            },
            {
                "LSTM": {"pH": 0.12, "TDS": 0.18, "temperature": 0.14, "turbidity": 0.13},
                "PatchTST": {"pH": 0.14, "TDS": 0.12, "temperature": 0.18, "turbidity": 0.15},
                "TimeMixer": {"pH": 0.18, "TDS": 0.16, "temperature": 0.12, "turbidity": 0.17},
            },
        ]

        config = WeightingConfig()
        weights = get_current_weights(error_history, config)

        # Check that weights are calculated
        self.assertIn("pH", weights)
        self.assertIn("TDS", weights)

        # Check that weights sum to 1
        for param in weights:
            param_total = sum(weights[param].values())
            self.assertAlmostEqual(param_total, 1.0, places=6)

    def test_get_current_weights_empty_history(self) -> None:
        """Test getting current weights from empty history."""
        error_history = []
        weights = get_current_weights(error_history)

        # Should return equal weights
        for param in weights:
            weights_list = list(weights[param].values())
            for i in range(len(weights_list) - 1):
                self.assertAlmostEqual(weights_list[i], weights_list[i + 1], places=6)


if __name__ == "__main__":
    unittest.main()
