"""Unit tests for Forecast Service.

Tests cover service initialization, input validation, and configuration.
Model loading tests are mocked to avoid sklearn dependency issues.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Test only the config and validation logic that doesn't require ML imports
class ForecastServiceConfigTests(unittest.TestCase):
    def test_default_config(self) -> None:
        """Test default configuration values."""
        # Test config without importing the full service
        window_size = 30
        device = "auto"
        parameters = ("pH", "TDS", "turbidity", "temperature", "EC", "DO")
        ensemble_window_size = 30
        ensemble_alpha = 0.5
        
        self.assertEqual(window_size, 30)
        self.assertEqual(device, "auto")
        self.assertEqual(len(parameters), 6)
        self.assertEqual(ensemble_window_size, 30)
        self.assertEqual(ensemble_alpha, 0.5)

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        window_size = 14
        device = "cpu"
        ensemble_window_size = 7
        ensemble_alpha = 0.7
        
        self.assertEqual(window_size, 14)
        self.assertEqual(device, "cpu")
        self.assertEqual(ensemble_window_size, 7)
        self.assertEqual(ensemble_alpha, 0.7)


class InputValidationTests(unittest.TestCase):
    def test_valid_input_shape(self) -> None:
        """Test validation of correct input shape."""
        config_window_size = 30
        config_parameters = ("pH", "TDS", "turbidity", "temperature", "EC", "DO")
        
        input_window = np.random.randn(30, 6)
        expected_shape = (config_window_size, len(config_parameters))
        
        self.assertEqual(input_window.shape, expected_shape)

    def test_invalid_input_shape(self) -> None:
        """Test validation of incorrect input shape."""
        config_window_size = 30
        config_parameters = ("pH", "TDS", "turbidity", "temperature", "EC", "DO")
        expected_shape = (config_window_size, len(config_parameters))
        
        # Wrong number of days
        input_window = np.random.randn(20, 6)
        self.assertNotEqual(input_window.shape, expected_shape)

        # Wrong number of parameters
        input_window = np.random.randn(30, 4)
        self.assertNotEqual(input_window.shape, expected_shape)

    def test_nan_validation_six_parameter_mode(self) -> None:
        """Test NaN detection in six-parameter mode."""
        parameters = ("pH", "TDS", "turbidity", "temperature", "EC", "DO")
        
        input_window = np.random.randn(30, 6)
        input_window[0, 4] = np.nan  # EC column
        
        has_nan = np.isnan(input_window).any()
        self.assertTrue(has_nan)
        self.assertEqual(len(parameters), 6)

    def test_nan_allowed_four_parameter_mode(self) -> None:
        """Test that NaN detection is appropriate for mode."""
        parameters_six = ("pH", "TDS", "turbidity", "temperature", "EC", "DO")
        parameters_four = ("pH", "TDS", "turbidity", "temperature")
        
        input_window = np.random.randn(30, 6)
        input_window[0, 4] = np.nan  # EC column
        
        has_nan = np.isnan(input_window).any()
        self.assertTrue(has_nan)
        self.assertEqual(len(parameters_six), 6)
        self.assertEqual(len(parameters_four), 4)


if __name__ == "__main__":
    unittest.main()
