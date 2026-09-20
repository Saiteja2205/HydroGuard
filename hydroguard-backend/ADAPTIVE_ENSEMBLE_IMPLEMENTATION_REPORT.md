# Adaptive Ensemble Implementation Report for HydroGuard Project

## Environment Information

- **Python Version**: 3.13.1
- **PyTorch Version**: 2.14.0+cpu
- **Operating System**: Windows
- **Platform**: Windows

## Files Created

1. **ml/ensemble/weighting.py** - Weight calculation module
2. **ml/ensemble/adaptive_ensemble.py** - Adaptive ensemble implementation
3. **ml/ensemble/__init__.py** - Ensemble module exports
4. **tests/test_adaptive_ensemble.py** - Comprehensive unit tests

## Files Modified

None (new module created)

## Adaptive Ensemble Architecture

### Purpose
Combines predictions from LSTM, PatchTST, and TimeMixer using adaptive inverse error weighting based on recent forecasting performance. This is a decision layer, not another neural network.

### Architecture Overview

```
Model Predictions (3 models × 6 parameters)
    ↓
Error Calculation (MAE + RMSE per model/parameter)
    ↓
Error Score: α × MAE + (1-α) × RMSE
    ↓
Inverse Error Weighting: weight_i = (1/(error_i + ε)) / Σ(1/(error_j + ε))
    ↓
Rolling Error History (default: 30 predictions)
    ↓
Weighted Combination: Final = Σ(w_i × prediction_i)
    ↓
Final Prediction (6 parameters)
```

### Weight Calculation Method

**Inverse Error Weighting:**
```
weight_i = (1 / (ErrorScore_i + epsilon)) / sum(1 / (ErrorScore_j + epsilon))
```

**Key Properties:**
- Lower error → higher weight
- Weights normalized to sum to 1
- Applied separately for each parameter
- No manually assigned weights

**Error Score Formula:**
```
ErrorScore = α × MAE + (1-α) × RMSE
```

- Default: α = 0.5 (equal weight to MAE and RMSE)
- Can be adjusted to favor one metric over the other

### Rolling Error History

**Purpose:** Smooth weight updates and avoid rapid fluctuations from single predictions.

**Configuration:**
- Default window_size: 30 predictions
- Supported window sizes: 7, 14, 30
- History truncation: Oldest entries removed when window exceeded

**Average Error Calculation:**
```
AverageError = (Σ error_history) / len(error_history)
```

### Example Weight Calculation

**Scenario:** Three models with different performance on temperature

```
Model Errors (Temperature):
- LSTM: MAE=0.3, RMSE=0.4 → ErrorScore=0.35
- PatchTST: MAE=0.5, RMSE=0.6 → ErrorScore=0.55
- TimeMixer: MAE=0.2, RMSE=0.3 → ErrorScore=0.25

Inverse Errors:
- LSTM: 1/0.35 = 2.857
- PatchTST: 1/0.55 = 1.818
- TimeMixer: 1/0.25 = 4.000

Total: 8.675

Normalized Weights:
- LSTM: 2.857/8.675 = 0.329
- PatchTST: 1.818/8.675 = 0.210
- TimeMixer: 4.000/8.675 = 0.461

Final Prediction = 0.329×LSTM + 0.210×PatchTST + 0.461×TimeMixer
```

### Parameter-Wise Weights

Each parameter gets its own weight distribution:

**Example:**
```
Temperature weights:
- LSTM: 0.33
- PatchTST: 0.21
- TimeMixer: 0.46

TDS weights (different distribution):
- LSTM: 0.40
- PatchTST: 0.35
- TimeMixer: 0.25
```

This allows the ensemble to leverage each model's strengths for different parameters.

## Implementation Features

### Weighting Module Features
- ✅ Configurable error score calculation (α parameter)
- ✅ Inverse error weighting with epsilon for stability
- ✅ Weight normalization (sum to 1)
- ✅ Min/max weight constraints (configurable)
- ✅ Parameter-wise weight calculation
- ✅ Rolling error history management
- ✅ Average error calculation over history
- ✅ Current weight calculation from history

### Adaptive Ensemble Features
- ✅ Configurable ensemble (model names, parameters, window size)
- ✅ Error calculation (MAE and RMSE per model/parameter)
- ✅ Error score combination
- ✅ Weight adaptation based on recent performance
- ✅ Prediction combination using current weights
- ✅ Error history tracking
- ✅ Rolling window management
- ✅ Weight reset functionality
- ✅ State management and summary

### Unit Tests
- ✅ Error score calculation tests
- ✅ Weight normalization tests
- ✅ Inverse error weighting tests
- ✅ Zero error handling tests
- ✅ Min/max weight constraint tests
- ✅ Parameter-wise weight calculation tests
- ✅ Different weights per parameter tests
- ✅ Error history update tests
- ✅ Rolling window truncation tests
- ✅ Average error calculation tests
- ✅ Empty history handling tests
- ✅ Weighted prediction combination tests
- ✅ Missing model handling tests
- ✅ Ensemble initialization tests
- ✅ Ensemble custom configuration tests
- ✅ Ensemble update from predictions tests
- ✅ Ensemble weight adaptation tests
- ✅ Ensemble combine predictions tests
- ✅ Ensemble reset weights tests
- ✅ Ensemble error history tracking tests
- ✅ Ensemble rolling window tests
- ✅ Ensemble get average errors tests
- ✅ Ensemble get summary tests
- ✅ Current weights from history tests
- ✅ Current weights empty history tests

## Test Results

### Adaptive Ensemble Tests (PASSED)
```
test_ensemble_combine_predictions ... ok
test_ensemble_custom_config ... ok
test_ensemble_error_history_tracking ... ok
test_ensemble_get_average_errors ... ok
test_ensemble_get_summary ... ok
test_ensemble_initialization ... ok
test_ensemble_reset_weights ... ok
test_ensemble_rolling_window ... ok
test_ensemble_update_from_predictions ... ok
test_ensemble_weight_adaptation ... ok
test_get_current_weights_empty_history ... ok
test_get_current_weights_from_history ... ok
test_average_errors_calculation ... ok
test_empty_history_handling ... ok
test_error_history_update ... ok
test_rolling_window_truncation ... ok
test_error_score_alpha_extremes ... ok
test_error_score_calculation ... ok
test_different_weights_per_parameter ... ok
test_parameter_wise_weight_calculation ... ok
test_missing_model_handling ... ok
test_weighted_prediction_combination ... ok
test_equal_errors_equal_weights ... ok
test_inverse_error_weighting ... ok
test_min_max_weight_constraints ... ok
test_weight_normalization ... ok
test_zero_error_handling ... ok

----------------------------------------------------------------------
Ran 27 tests in 0.003s
OK
```

## Configuration

### Default WeightingConfig
```python
WeightingConfig(
    alpha: float = 0.5,           # MAE weight in error score
    epsilon: float = 1e-8,         # Stability constant
    window_size: int = 30,         # Rolling window size
    min_weight: float = 0.05,      # Minimum weight per model
    max_weight: float = 0.9,       # Maximum weight per model
)
```

### Default AdaptiveEnsembleConfig
```python
AdaptiveEnsembleConfig(
    model_names: tuple[str, ...] = ("LSTM", "PatchTST", "TimeMixer"),
    parameters: tuple[str, ...] = ("pH", "TDS", "turbidity", "temperature", "EC", "DO"),
    alpha: float = 0.5,
    epsilon: float = 1e-8,
    window_size: int = 30,
    min_weight: float = 0.05,
    max_weight: float = 0.9,
)
```

## Usage Example

```python
from ml.ensemble import create_ensemble, AdaptiveEnsembleConfig

# Create ensemble with custom configuration
config = AdaptiveEnsembleConfig(
    window_size=14,
    alpha=0.7,  # Favor MAE over RMSE
    min_weight=0.1,
    max_weight=0.8,
)
ensemble = create_ensemble(config)

# Update ensemble with new predictions
predictions = {
    "LSTM": {"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "EC": 500.0, "DO": 8.0},
    "PatchTST": {"pH": 7.2, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "EC": 510.0, "DO": 8.2},
    "TimeMixer": {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "EC": 505.0, "DO": 8.1},
}
ground_truth = {"pH": 7.1, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "EC": 505.0, "DO": 8.1}

# Update weights based on performance
weights = ensemble.update_from_predictions(predictions, ground_truth)

# Get current weights
current_weights = ensemble.get_current_weights()

# Combine predictions
combined = ensemble.combine(predictions)

# Get ensemble summary
summary = ensemble.get_summary()
```

## Verification of Existing Models

### Existing Models (UNCHANGED)
```
============================================================
EXISTING MODELS VERIFICATION (UNCHANGED)
============================================================

LSTM Model:
  Parameters: 52102
  Architecture: (batch, 30, 6) -> LSTM -> Linear -> (batch, 6)
  UNCHANGED

PatchTST Model:
  Parameters: 589318
  Architecture: (batch, 30, 6) -> Patches -> Transformer -> (batch, 6)
  UNCHANGED

TimeMixer Model:
  Parameters: 194374
  Architecture: (batch, 30, 6) -> Multi-Scale -> Mixing -> (batch, 6)
  UNCHANGED

============================================================
EXISTING MODELS UNCHANGED
============================================================
```

## Important Notes

### Not a Neural Network
- The Adaptive Ensemble is a decision layer, not another neural network
- It uses mathematical operations (inverse error weighting) rather than learned parameters
- No training is required for the ensemble itself
- It adapts based on the performance of the underlying models

### EC and DO Handling
- The ensemble follows the same rules as individual models
- It will receive predictions that have NaN for unavailable parameters
- The ensemble will propagate NaN values appropriately in weighted combinations
- EC and DO are never fabricated

### No Accuracy Claims
- The implementation uses synthetic/dummy data for testing
- No real performance claims are made until the ensemble is evaluated with real data
- Weight adaptation is demonstrated with test cases but not real performance

### Android Integration
- **NOT MODIFIED** - Android application was not touched as requested
- All work was focused on the backend ensemble implementation

### FastAPI Integration
- **NOT IMPLEMENTED** - FastAPI forecast endpoint was not implemented as requested
- The ensemble can be integrated into FastAPI in future work

### What Was NOT Implemented
- ❌ API integration
- ❌ Android integration
- ❌ ESP32 integration
- ❌ New forecasting models

## Remaining Work

1. **Integration with Model Predictions**: Connect ensemble to actual LSTM, PatchTST, and TimeMixer predictions
2. **Real Data Evaluation**: Test ensemble performance with actual water quality measurements
3. **Hyperparameter Tuning**: Optimize window_size, alpha, min_weight, max_weight
4. **FastAPI Integration**: Add ensemble endpoint to FastAPI backend
5. **Performance Benchmarking**: Compare ensemble vs individual models
6. **Four-Parameter Mode**: Test ensemble with four-parameter development mode

## Summary

The Adaptive Ensemble implementation is complete with:

- ✅ Inverse error weighting method (not manual weights)
- ✅ Parameter-wise weight calculation
- ✅ Rolling error history management (configurable window sizes)
- ✅ MAE and RMSE error calculation
- ✅ Weight normalization (sum to 1)
- ✅ Lower error → higher weight behavior
- ✅ Zero error handling with epsilon
- ✅ Min/max weight constraints
- ✅ Comprehensive test suite (27/27 passed)
- ✅ LSTM model preserved unchanged (52,102 parameters)
- ✅ PatchTST model preserved unchanged (589,318 parameters)
- ✅ TimeMixer model preserved unchanged (194,374 parameters)
- ✅ Android project not modified
- ✅ FastAPI backend not modified

The ensemble provides a decision layer that dynamically adapts model contributions based on recent forecasting performance, offering a robust approach to combine the strengths of LSTM, PatchTST, and TimeMixer models for water quality forecasting.
