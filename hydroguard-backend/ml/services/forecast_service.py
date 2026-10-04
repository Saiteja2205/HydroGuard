"""Forecast Service for HydroGuard water quality forecasting.

Orchestrates the complete forecasting workflow:
1. Load trained model checkpoints
2. Accept historical water quality window
3. Generate individual predictions
4. Combine predictions using Adaptive Ensemble
5. Return final forecast output
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import torch

try:
    from ml.data import run_pipeline, PipelineConfig, PipelineResult
except ImportError:
    # Fallback if sklearn is not available
    PipelineConfig = None
    PipelineResult = None
    run_pipeline = None

try:
    from ml.prediction.predict_lstm import load_model_for_prediction as load_lstm
except ImportError:
    load_lstm = None

try:
    from ml.prediction.predict_patchtst import load_model_for_prediction as load_patchtst
except ImportError:
    load_patchtst = None

try:
    from ml.prediction.predict_timemixer import load_model_for_prediction as load_timemixer
except ImportError:
    load_timemixer = None

try:
    from ml.ensemble import create_ensemble, AdaptiveEnsembleConfig
except ImportError:
    create_ensemble = None
    AdaptiveEnsembleConfig = None


@dataclass
class ForecastServiceConfig:
    """Configuration for ForecastService."""

    lstm_checkpoint_path: str = "artifacts/checkpoints/lstm_water_quality_best.pt"
    patchtst_checkpoint_path: str = "artifacts/checkpoints/patchtst_water_quality_best.pt"
    timemixer_checkpoint_path: str = "artifacts/checkpoints/timemixer_water_quality_best.pt"
    device: str = "auto"
    window_size: int = 30
    parameters: tuple[str, ...] = ("pH", "TDS", "turbidity", "temperature")
    ensemble_window_size: int = 30
    ensemble_alpha: float = 0.5
    four_parameter_mode: bool = True  # Optical colour has no validated checkpoint yet.


class ForecastService:
    """Service for orchestrating complete forecasting workflow."""

    def __init__(self, config: ForecastServiceConfig | None = None):
        self.config = config or ForecastServiceConfig()
        self.models_loaded = False
        self.lstm_model = None
        self.patchtst_model = None
        self.timemixer_model = None
        self.ensemble = None
        self.pipeline_result = None
        self.device = None

    def load_models(self) -> None:
        """Load all trained model checkpoints."""
        # Determine device
        if self.config.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = self.config.device
        self.device = torch.device(self.device)

        # Try to use prediction helpers first (full pipeline)
        use_prediction_helpers = False
        if load_lstm and load_patchtst and load_timemixer:
            try:
                # Load LSTM
                lstm_path = Path(self.config.lstm_checkpoint_path)
                if not lstm_path.exists():
                    raise FileNotFoundError(f"LSTM checkpoint not found: {lstm_path}")
                self.lstm_model, _ = load_lstm(lstm_path, device=self.device)

                # Load PatchTST
                patchtst_path = Path(self.config.patchtst_checkpoint_path)
                if not patchtst_path.exists():
                    raise FileNotFoundError(f"PatchTST checkpoint not found: {patchtst_path}")
                self.patchtst_model, _ = load_patchtst(patchtst_path, device=self.device)

                # Load TimeMixer
                timemixer_path = Path(self.config.timemixer_checkpoint_path)
                if not timemixer_path.exists():
                    raise FileNotFoundError(f"TimeMixer checkpoint not found: {timemixer_path}")
                self.timemixer_model, _ = load_timemixer(timemixer_path, device=self.device)
                use_prediction_helpers = True
            except (KeyError, TypeError) as e:
                # Fallback to direct loading if checkpoint config is incomplete
                print(f"Warning: Prediction helpers failed due to incomplete checkpoint config: {e}")
                print("Falling back to direct model loading...")
                use_prediction_helpers = False
        
        if not use_prediction_helpers:
            # Fallback: load models directly (for four-parameter demo mode)
            from ml.models.lstm_model import LSTMModel
            from ml.models.patchtst_model import PatchTST
            from ml.models.timemixer_model import TimeMixer
            
            # Load LSTM
            lstm_path = Path(self.config.lstm_checkpoint_path)
            if not lstm_path.exists():
                raise FileNotFoundError(f"LSTM checkpoint not found: {lstm_path}")
            checkpoint = torch.load(lstm_path, map_location=self.device)
            input_size = checkpoint.get('config', {}).get('input_size', len(self.config.parameters))
            output_size = checkpoint.get('config', {}).get('output_size', input_size)
            # Use default values for missing parameters
            self.lstm_model = LSTMModel(
                input_size=input_size,
                hidden_size=64,
                num_layers=2,
                dropout=0.2,
                output_size=output_size,
            )
            self.lstm_model.load_state_dict(checkpoint['model_state_dict'])
            self.lstm_model.to(self.device)
            self.lstm_model.eval()

            # Load PatchTST
            patchtst_path = Path(self.config.patchtst_checkpoint_path)
            if not patchtst_path.exists():
                raise FileNotFoundError(f"PatchTST checkpoint not found: {patchtst_path}")
            checkpoint = torch.load(patchtst_path, map_location=self.device)
            input_size = checkpoint.get('config', {}).get('input_size', len(self.config.parameters))
            output_size = checkpoint.get('config', {}).get('output_size', input_size)
            # Use default values for missing parameters
            self.patchtst_model = PatchTST(
                input_size=input_size,
                context_length=30,
                patch_length=5,
                stride=5,
                d_model=64,
                num_heads=4,
                num_layers=2,
                dropout=0.1,
                output_size=output_size,
            )
            self.patchtst_model.load_state_dict(checkpoint['model_state_dict'])
            self.patchtst_model.to(self.device)
            self.patchtst_model.eval()

            # Load TimeMixer
            timemixer_path = Path(self.config.timemixer_checkpoint_path)
            if not timemixer_path.exists():
                raise FileNotFoundError(f"TimeMixer checkpoint not found: {timemixer_path}")
            checkpoint = torch.load(timemixer_path, map_location=self.device)
            input_size = checkpoint.get('config', {}).get('input_size', len(self.config.parameters))
            output_size = checkpoint.get('config', {}).get('output_size', input_size)
            # Use default values for missing parameters
            self.timemixer_model = TimeMixer(
                input_size=input_size,
                context_length=30,
                hidden_size=64,
                num_scales=3,
                num_mixing_layers=2,
                dropout=0.1,
                output_size=output_size,
            )
            self.timemixer_model.load_state_dict(checkpoint['model_state_dict'])
            self.timemixer_model.to(self.device)
            self.timemixer_model.eval()

        # Initialize ensemble
        if create_ensemble and AdaptiveEnsembleConfig:
            ensemble_config = AdaptiveEnsembleConfig(
                window_size=self.config.ensemble_window_size,
                alpha=self.config.ensemble_alpha,
                parameters=self.config.parameters,  # Use the service's parameters
            )
            self.ensemble = create_ensemble(ensemble_config)
        else:
            # Fallback ensemble
            self.ensemble = None

        self.models_loaded = True

    def validate_input_shape(self, input_window: np.ndarray) -> None:
        """Validate input window shape and content.

        Args:
            input_window: Input array of shape (window_size, num_parameters)

        Raises:
            ValueError: If shape, finiteness, or observation completeness is invalid
        """
        expected_shape = (self.config.window_size, len(self.config.parameters))

        if input_window.shape != expected_shape:
            raise ValueError(
                f"Expected input shape {expected_shape}, got {input_window.shape}. "
                f"Need {self.config.window_size} days × {len(self.config.parameters)} parameters."
            )

        if not np.isfinite(input_window).all():
            raise ValueError("Forecast history contains missing or non-finite values.")

    def normalize_input(
        self,
        input_window: np.ndarray,
        pipeline_result: PipelineResult,
    ) -> np.ndarray:
        """Normalize input window using the pipeline scaler.

        Args:
            input_window: Raw input window (window_size, num_parameters)
            pipeline_result: Pipeline result with scaler

        Returns:
            Normalized input window
        """
        # Reshape for scaler: (window_size, num_parameters)
        scaled = pipeline_result.scaler.transform(input_window)
        return scaled

    def get_individual_predictions(
        self,
        normalized_input: np.ndarray,
    ) -> dict[str, dict[str, float]]:
        """Get predictions from all individual models.

        Args:
            normalized_input: Normalized input window (window_size, num_parameters)

        Returns:
            Dictionary of model predictions per parameter
        """
        # Add batch dimension: (1, window_size, num_parameters)
        input_batch = normalized_input[np.newaxis, ...]

        # LSTM prediction
        with torch.no_grad():
            lstm_output = self.lstm_model(torch.from_numpy(input_batch).float().to(self.device))
            lstm_pred = lstm_output.cpu().numpy()[0]

        # PatchTST prediction
        with torch.no_grad():
            patchtst_output = self.patchtst_model(torch.from_numpy(input_batch).float().to(self.device))
            patchtst_pred = patchtst_output.cpu().numpy()[0]

        # TimeMixer prediction
        with torch.no_grad():
            timemixer_output = self.timemixer_model(torch.from_numpy(input_batch).float().to(self.device))
            timemixer_pred = timemixer_output.cpu().numpy()[0]

        # Create prediction dictionaries
        predictions = {
            "LSTM": {param: float(pred) for param, pred in zip(self.config.parameters, lstm_pred)},
            "PatchTST": {param: float(pred) for param, pred in zip(self.config.parameters, patchtst_pred)},
            "TimeMixer": {param: float(pred) for param, pred in zip(self.config.parameters, timemixer_pred)},
        }

        return predictions

    def inverse_transform_predictions(
        self,
        scaled_predictions: dict[str, dict[str, float]],
        pipeline_result: PipelineResult,
    ) -> dict[str, dict[str, float]]:
        """Inverse transform predictions back to physical units.

        Args:
            scaled_predictions: Scaled predictions from models
            pipeline_result: Pipeline result with scaler

        Returns:
            Physical predictions per model and parameter
        """
        physical_predictions = {}

        for model_name, model_preds in scaled_predictions.items():
            # Convert to array for inverse transform
            pred_array = np.array([model_preds[param] for param in self.config.parameters]).reshape(1, -1)
            physical_array = pipeline_result.scaler.inverse_transform(pred_array)[0]

            physical_predictions[model_name] = {
                param: float(value) for param, value in zip(self.config.parameters, physical_array)
            }

        return physical_predictions

    def generate_forecast(
        self,
        input_window: np.ndarray,
        pipeline_result: PipelineResult | None = None,
    ) -> dict[str, Any]:
        """Generate complete forecast with ensemble combination.

        Args:
            input_window: Historical water quality window (window_size, num_parameters)
            pipeline_result: Pipeline result with scaler (if None, creates minimal pipeline)

        Returns:
            Complete forecast response with predictions and weights
        """
        if not self.models_loaded:
            self.load_models()

        # Validate input
        self.validate_input_shape(input_window)

        # Use provided pipeline or create minimal one for scaling
        if pipeline_result is None:
            # Create minimal pipeline for scaling only
            pipeline_config = PipelineConfig(parameters=self.config.parameters)
            # Note: This is a simplified approach - in production, use the same pipeline
            # that was used during training to ensure consistent scaling
            # For now, we'll use a simple standardization
            try:
                from sklearn.preprocessing import StandardScaler
                scaler = StandardScaler()
                scaler.fit(input_window)
            except ImportError:
                # Fallback if sklearn is not available (for testing)
                # Use simple z-score normalization
                scaler = None
                
            if scaler is not None:
                class SimplePipelineResult:
                    def __init__(self, scaler, parameters):
                        self.scaler = scaler
                        self.config = type('obj', (object,), {'parameters': parameters})()
                
                pipeline_result = SimplePipelineResult(scaler, self.config.parameters)
            else:
                # Fallback: simple normalization without sklearn
                class SimplePipelineResult:
                    def __init__(self, parameters):
                        mean = input_window.mean(axis=0)
                        std = input_window.std(axis=0)
                        std[std == 0] = 1.0  # Avoid division by zero
                        
                        class SimpleScaler:
                            def transform(self, data):
                                return (data - mean) / std
                            
                            def inverse_transform(self, data):
                                return data * std + mean
                        
                        self.scaler = SimpleScaler()
                        self.config = type('obj', (object,), {'parameters': parameters})()
                
                pipeline_result = SimplePipelineResult(self.config.parameters)

        # Normalize input
        normalized_input = self.normalize_input(input_window, pipeline_result)

        # Get individual predictions
        scaled_predictions = self.get_individual_predictions(normalized_input)

        # Inverse transform to physical units
        physical_predictions = self.inverse_transform_predictions(scaled_predictions, pipeline_result)

        # Combine using ensemble
        # Note: In production, you would update ensemble with ground truth feedback
        # For now, we use current weights (equal distribution initially)
        final_prediction = self.ensemble.combine(physical_predictions)

        # Get current weights
        current_weights = self.ensemble.get_current_weights()

        # Build response
        forecast_date = datetime.now(timezone.utc)

        response = {
            "forecast_date": forecast_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "prediction": final_prediction,
            "model_predictions": physical_predictions,
            "weights": current_weights,
            "model_versions": {
                "LSTM": self._checkpoint_version(self.config.lstm_checkpoint_path),
                "PatchTST": self._checkpoint_version(self.config.patchtst_checkpoint_path),
                "TimeMixer": self._checkpoint_version(self.config.timemixer_checkpoint_path),
            },
        }

        return response

    @staticmethod
    def _checkpoint_version(path: str) -> str:
        """Return a stable content identifier for the exact checkpoint used."""
        checkpoint_path = Path(path)
        digest = hashlib.sha256()
        with checkpoint_path.open("rb") as checkpoint_file:
            for chunk in iter(lambda: checkpoint_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"{checkpoint_path.name}@sha256:{digest.hexdigest()[:16]}"

    def update_ensemble(
        self,
        predictions: dict[str, dict[str, float]],
        ground_truth: dict[str, float],
    ) -> dict[str, dict[str, float]]:
        """Update ensemble weights based on actual ground truth.

        Args:
            predictions: Model predictions for the previous forecast
            ground_truth: Actual measured values

        Returns:
            Updated weights
        """
        if not self.models_loaded:
            raise RuntimeError("Models must be loaded before updating ensemble")

        return self.ensemble.update_from_predictions(predictions, ground_truth)

    def get_model_status(self) -> dict[str, bool]:
        """Get loading status of all models.

        Returns:
            Dictionary with model loading status
        """
        return {
            "lstm": self.lstm_model is not None,
            "patchtst": self.patchtst_model is not None,
            "timemixer": self.timemixer_model is not None,
        }


def create_forecast_service(config: ForecastServiceConfig | None = None) -> ForecastService:
    """Factory function to create a ForecastService.

    Args:
        config: Service configuration

    Returns:
        Initialized ForecastService instance
    """
    return ForecastService(config)
