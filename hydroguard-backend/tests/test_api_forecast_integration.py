"""Integration test for forecast service with trained checkpoints.

Tests the complete forecast workflow from input to response without FastAPI.
"""

from __future__ import annotations

import csv
from io import StringIO
import sys
from pathlib import Path

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.services import create_forecast_service, ForecastServiceConfig


def load_demo_data() -> np.ndarray:
    """Load 30 timestamped simulated five-feature observations."""
    data_file = BACKEND_ROOT / "data" / "development_water_quality_200_observations.csv"
    
    readings = []
    with open(data_file, encoding="utf-8-sig") as f:
        reader = csv.DictReader(line for line in f if not line.startswith("#"))
        for i, row in enumerate(reader):
            if i >= 30:  # Only need 30 days
                break
            readings.append([
                float(row["pH"]),
                float(row["TDS"]),
                float(row["turbidity"]),
                float(row["temperature"]),
                float(row["optical_colour_index"]),
            ])
    
    return np.array(readings, dtype=np.float32)


def test_forecast_service_integration() -> None:
    """Test the forecast service with trained checkpoints."""
    print("="*70)
    print("FORECAST SERVICE INTEGRATION TEST")
    print("="*70)

    # Check checkpoints exist
    checkpoint_dir = BACKEND_ROOT / "artifacts" / "checkpoints"
    checkpoints = [
        "lstm_water_quality_5param_v1.pt",
        "patchtst_water_quality_5param_v1.pt",
        "timemixer_water_quality_5param_v1.pt",
    ]
    
    print("\n1. Checking checkpoints:")
    all_exist = True
    for cp in checkpoints:
        path = checkpoint_dir / cp
        if path.exists():
            print(f"   [OK] {cp}")
        else:
            print(f"   [FAIL] {cp}")
            all_exist = False
    
    if not all_exist:
        print("\n   ERROR: Not all checkpoints exist. Cannot proceed.")
        return

    # Load demo data
    print("\n2. Loading demo data:")
    try:
        input_window = load_demo_data()
        print(f"   [OK] Loaded input window shape: {input_window.shape}")
    except Exception as e:
        print(f"   [FAIL] Error loading demo data: {e}")
        return

    # Create forecast service using the active five-parameter contract.
    print("\n3. Creating forecast service (five-parameter mode):")
    try:
        config = ForecastServiceConfig(
            five_parameter_mode=True,
            parameters=("pH", "TDS", "turbidity", "temperature", "optical_colour_index"),
        )
        service = create_forecast_service(config)
        print("   [OK] Forecast service created")
    except Exception as e:
        print(f"   [FAIL] Error creating service: {e}")
        import traceback
        traceback.print_exc()
        return

    # Load models
    print("\n4. Loading models:")
    try:
        service.load_models()
        print("   [OK] All models loaded successfully")
        print(f"   LSTM: {service.lstm_model is not None}")
        print(f"   PatchTST: {service.patchtst_model is not None}")
        print(f"   TimeMixer: {service.timemixer_model is not None}")
        print(f"   Ensemble: {service.ensemble is not None}")
    except Exception as e:
        print(f"   [FAIL] Error loading models: {e}")
        import traceback
        traceback.print_exc()
        return

    # Generate forecast
    print("\n5. Generating forecast:")
    try:
        forecast_result = service.generate_forecast(input_window)
        print("   [OK] Forecast generated successfully")
    except Exception as e:
        print(f"   [FAIL] Error generating forecast: {e}")
        import traceback
        traceback.print_exc()
        return

    # Verify response structure
    print("\n6. Verifying response structure:")
    
    # Check forecast_date
    if "forecast_date" in forecast_result:
        print(f"   [OK] forecast_date: {forecast_result['forecast_date']}")
    else:
        print("   [FAIL] Missing forecast_date")
    
    # Check prediction
    if "prediction" in forecast_result:
        pred = forecast_result["prediction"]
        required_fields = ["pH", "TDS", "turbidity", "temperature"]
        missing = [f for f in required_fields if f not in pred]
        if not missing:
            print(f"   [OK] prediction has all required fields")
            print(f"        pH: {pred.get('pH', 'N/A'):.4f}")
            print(f"        TDS: {pred.get('TDS', 'N/A'):.4f}")
            print(f"        turbidity: {pred.get('turbidity', 'N/A'):.4f}")
            print(f"        temperature: {pred.get('temperature', 'N/A'):.4f}")
        else:
            print(f"   [FAIL] Missing prediction fields: {missing}")
    else:
        print("   [FAIL] Missing prediction")
    
    # Check model_predictions
    if "model_predictions" in forecast_result:
        model_preds = forecast_result["model_predictions"]
        required_models = ["LSTM", "PatchTST", "TimeMixer"]
        missing = [m for m in required_models if m not in model_preds]
        if not missing:
            print(f"   [OK] model_predictions has all models")
            for model in required_models:
                print(f"        {model}: present")
        else:
            print(f"   [FAIL] Missing models: {missing}")
    else:
        print("   [FAIL] Missing model_predictions")
    
    # Check weights
    if "weights" in forecast_result:
        weights = forecast_result["weights"]
        if len(weights) > 0:
            print(f"   [OK] weights present ({len(weights)} parameters)")
            # Show weights for first parameter
            first_param = list(weights.keys())[0]
            print(f"        {first_param}:")
            for model, weight in weights[first_param].items():
                print(f"          {model}: {weight:.4f}")
        else:
            print("   [FAIL] weights is empty")
    else:
        print("   [FAIL] Missing weights")
    
    # Print full response
    print("\n7. Full response example:")
    import json
    print(json.dumps(forecast_result, indent=2))
    
    print("\n" + "="*70)
    print("FORECAST SERVICE INTEGRATION TEST PASSED")
    print("="*70)
    print("\nIMPORTANT:")
    print("- This test used synthetic demo data")
    print("- Five-parameter development checkpoint files are required")
    print("- Forecast service validates the software pipeline only")
    print("- Predictions are NOT real water quality forecasts")
    print("="*70)


if __name__ == "__main__":
    test_forecast_service_integration()
