"""End-to-end forecast test for HydroGuard ML pipeline.

Tests the complete workflow from trained models to forecast generation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.models.lstm_model import LSTMModel
from ml.models.patchtst_model import PatchTST
from ml.models.timemixer_model import TimeMixer
from ml.ensemble import create_ensemble, AdaptiveEnsembleConfig


def test_end_to_end_forecast() -> None:
    """Test end-to-end forecast with trained models."""
    print("="*70)
    print("END-TO-END FORECAST TEST")
    print("="*70)

    # Configuration
    checkpoint_dir = Path("artifacts/checkpoints")
    parameters = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")
    input_size = 5
    window_size = 30

    # Check checkpoints exist
    lstm_checkpoint = checkpoint_dir / "lstm_water_quality_5param_v1.pt"
    patchtst_checkpoint = checkpoint_dir / "patchtst_water_quality_5param_v1.pt"
    timemixer_checkpoint = checkpoint_dir / "timemixer_water_quality_5param_v1.pt"

    print("\n1. Checking checkpoints:")
    for path in [lstm_checkpoint, patchtst_checkpoint, timemixer_checkpoint]:
        if path.exists():
            print(f"   [OK] {path}")
        else:
            print(f"   [FAIL] {path}")
            return

    # Load models
    print("\n2. Loading models:")
    try:
        lstm_model = LSTMModel(input_size=input_size, output_size=input_size)
        lstm_checkpoint_data = torch.load(lstm_checkpoint, map_location='cpu')
        lstm_model.load_state_dict(lstm_checkpoint_data['model_state_dict'])
        lstm_model.eval()
        print("   [OK] LSTM loaded")

        patchtst_model = PatchTST(input_size=input_size, output_size=input_size)
        patchtst_checkpoint_data = torch.load(patchtst_checkpoint, map_location='cpu')
        patchtst_model.load_state_dict(patchtst_checkpoint_data['model_state_dict'])
        patchtst_model.eval()
        print("   [OK] PatchTST loaded")

        timemixer_model = TimeMixer(input_size=input_size, output_size=input_size)
        timemixer_checkpoint_data = torch.load(timemixer_checkpoint, map_location='cpu')
        timemixer_model.load_state_dict(timemixer_checkpoint_data['model_state_dict'])
        timemixer_model.eval()
        print("   [OK] TimeMixer loaded")
    except Exception as e:
        print(f"   [FAIL] Error loading models: {e}")
        return

    # Initialize ensemble
    print("\n3. Initializing ensemble:")
    try:
        ensemble_config = AdaptiveEnsembleConfig(
            model_names=("LSTM", "PatchTST", "TimeMixer"),
            parameters=parameters,
        )
        ensemble = create_ensemble(ensemble_config)
        print("   [OK] Ensemble initialized")
    except Exception as e:
        print(f"   [FAIL] Error initializing ensemble: {e}")
        return

    # Generate test input (30 days of synthetic data)
    print("\n4. Generating test input (30 days):")
    X_test = np.random.randn(1, window_size, input_size).astype(np.float32)
    print(f"   Input shape: {X_test.shape}")

    # Get individual predictions
    print("\n5. Generating individual predictions:")
    try:
        with torch.no_grad():
            lstm_pred = lstm_model(torch.from_numpy(X_test).float())[0].numpy()
            patchtst_pred = patchtst_model(torch.from_numpy(X_test).float())[0].numpy()
            timemixer_pred = timemixer_model(torch.from_numpy(X_test).float())[0].numpy()
        print("   [OK] Individual predictions generated")
    except Exception as e:
        print(f"   [FAIL] Error generating predictions: {e}")
        return

    # Combine predictions
    print("\n6. Combining predictions with ensemble:")
    try:
        predictions = {
            "LSTM": {param: float(pred) for param, pred in zip(parameters, lstm_pred)},
            "PatchTST": {param: float(pred) for param, pred in zip(parameters, patchtst_pred)},
            "TimeMixer": {param: float(pred) for param, pred in zip(parameters, timemixer_pred)},
        }
        combined = ensemble.combine(predictions)
        print("   [OK] Combined prediction generated")
    except Exception as e:
        print(f"   [FAIL] Error combining predictions: {e}")
        return

    # Verify output structure
    print("\n7. Verifying output structure:")
    try:
        # Check combined prediction
        for param in parameters:
            if param not in combined:
                print(f"   [FAIL] Missing parameter in combined: {param}")
                return
        print("   [OK] Combined prediction has all parameters")

        # Check individual predictions
        for model_name in ["LSTM", "PatchTST", "TimeMixer"]:
            for param in parameters:
                if param not in predictions[model_name]:
                    print(f"   [FAIL] Missing parameter in {model_name}: {param}")
                    return
        print("   [OK] Individual predictions have all parameters")

        # Check weights
        weights = ensemble.get_current_weights()
        for param in parameters:
            if param not in weights:
                print(f"   [FAIL] Missing parameter in weights: {param}")
                return
            total_weight = sum(weights[param].values())
            if not (0.99 <= total_weight <= 1.01):
                print(f"   [FAIL] Weights don't sum to 1 for {param}: {total_weight}")
                return
        print("   [OK] Weights normalized correctly")
    except Exception as e:
        print(f"   [FAIL] Error verifying output: {e}")
        return

    # Print sample output
    print("\n8. Sample output:")
    print(f"   Combined prediction:")
    for param, value in combined.items():
        print(f"     {param}: {value:.4f}")

    print(f"\n   Weights (for {parameters[0]}):")
    for model, weight in weights[parameters[0]].items():
        print(f"     {model}: {weight:.4f}")

    print("\n" + "="*70)
    print("END-TO-END FORECAST TEST PASSED")
    print("="*70)
    print("\nIMPORTANT:")
    print("- This test used synthetic test input")
    print("- Predictions are NOT real water quality forecasts")
    print("- This validates the software pipeline only")
    print("="*70)


if __name__ == "__main__":
    test_end_to_end_forecast()
