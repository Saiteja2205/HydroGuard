# PatchTST Implementation Report for HydroGuard Project

> Historical report: these original results refer to the former four-feature simulated models and are superseded by the active five-feature development pipeline described in `README.md`.

## Environment Information

- **Python Version**: 3.13.1
- **PyTorch Version**: 2.14.0+cpu
- **Operating System**: Windows
- **Platform**: Windows

## Files Created

1. **ml/models/patchtst_model.py** - PatchTST model architecture
2. **ml/training/train_patchtst.py** - Training pipeline with early stopping
3. **ml/prediction/predict_patchtst.py** - Prediction and evaluation functions
4. **tests/test_patchtst_model.py** - Comprehensive unit tests

## Files Modified

1. **ml/models/__init__.py** - Added PatchTST export
2. **ml/training/__init__.py** - Added PatchTST training exports
3. **ml/prediction/__init__.py** - Added PatchTST prediction exports

## PatchTST Architecture

### Model Specification
Based on "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers"

**Default Configuration:**
- **Input Shape**: (batch, 30, 6) - 30 days of 6 parameters
- **Patch Length**: 5
- **Stride**: 5
- **Number of Patches**: 6 (calculated as (30-5)//5 + 1)
- **Patch Embedding**: Linear(patch_length * input_size, d_model) = Linear(30, 64)
- **Positional Encoding**: Sinusoidal positional encoding
- **Transformer Encoder**: 
  - d_model = 64
  - num_heads = 4
  - num_layers = 2
  - dropout = 0.1
- **Prediction Head**: Sequential(Linear(384, 64), ReLU, Dropout(0.1), Linear(64, 6))
- **Final Output Shape**: (batch, 6)
- **Total Parameters**: 589,318

### Architecture Flow
```
Input: (batch, 30, 6)
    â†“
Patch Creation: (batch, 6, 30) - 6 patches of 5 timesteps Ã— 6 features
    â†“
Patch Embedding: (batch, 6, 64) - Linear projection to d_model
    â†“
Positional Encoding: (batch, 6, 64) - Add positional information
    â†“
Transformer Encoder: (batch, 6, 64) - Multi-head self-attention
    â†“
Flatten: (batch, 384) - 6 patches Ã— 64 dimensions
    â†“
Prediction Head: (batch, 6) - Linear projection to output
    â†“
Output: (batch, 6) - Next day's 6 parameters
```

### Six Parameters (Default)
The model outputs six water quality parameters:
1. pH
2. TDS (Total Dissolved Solids)
3. turbidity
4. temperature
5. EC (Electrical Conductivity)
6. DO (Dissolved Oxygen)

### Four-Parameter Development Mode
An explicit four-parameter mode is available for development when EC/DO sensors are not available:
- Parameters: [pH, TDS, turbidity, temperature]
- Activated via `four_param_mode=True` in PatchTSTTrainingConfig
- **EC and DO are NEVER fabricated** - they remain unavailable

## Implementation Features

### Training Features
- âœ… Configurable model class (patch_length, stride, d_model, num_heads, num_layers, dropout)
- âœ… Deterministic random seed (set_random_seed)
- âœ… PyTorch DataLoader
- âœ… Training loop with MSE loss
- âœ… Validation loss tracking
- âœ… Early stopping (configurable patience)
- âœ… Best checkpoint saving
- âœ… Checkpoint loading
- âœ… CPU support
- âœ… Optional CUDA detection (auto)
- âœ… Learning rate scheduling (Adam optimizer)
- âœ… CLI argument support
- âœ… Reuses existing HydroGuard data pipeline

### Prediction Features
- âœ… Prediction function
- âœ… Inverse transformation using existing scaler
- âœ… Parameter dictionary output (predict_as_dict)
- âœ… MAE (Mean Absolute Error) calculation
- âœ… RMSE (Root Mean Square Error) calculation
- âœ… Test set evaluation
- âœ… Model loading from checkpoint
- âœ… Device handling (auto/cpu/cuda)

### Unit Tests
- âœ… Model initialization tests (default and custom)
- âœ… Patch creation shape tests
- âœ… Forward pass shape tests
- âœ… Four-parameter mode tests
- âœ… Architecture component tests
- âœ… Checkpoint save/load tests
- âœ… Device selection tests
- âœ… Batch size variation tests
- âœ… Gradient flow tests
- âœ… NaN validation logic tests
- âœ… Positional encoding tests

## Test Results

### PatchTST Model Tests (PASSED)
```
test_architecture_components ... ok
test_patch_embedding_dimensions ... ok
test_prediction_head_dimensions ... ok
test_checkpoint_save_load ... ok
test_auto_device_resolution ... ok
test_cpu_device ... ok
test_four_parameter_model ... ok
test_four_parameter_patch_creation ... ok
test_clean_data_detection ... ok
test_nan_detection_logic ... ok
test_different_batch_sizes ... ok
test_end_to_end_forward_pass ... ok
test_gradient_flow ... ok
test_forward_pass_four_param ... ok
test_forward_pass_shape ... ok
test_model_initialization_custom ... ok
test_model_initialization_default ... ok
test_model_parameter_count ... ok
test_num_patches_calculation ... ok
test_patch_creation_shape ... ok
test_positional_encoding_shape ... ok

----------------------------------------------------------------------
Ran 21 tests in 1.723s
OK
```

### Architecture Verification (PASSED)
```
============================================================
PATCHTST MODEL ARCHITECTURE VERIFICATION
============================================================

Test 1: Model initialization
  Input size: 6
  Context length: 30
  Patch length: 5
  Stride: 5
  D model: 64
  Num heads: 4
  Num layers: 2
  Dropout: 0.1
  Output size: 6
  Number of patches: 6
  Total parameters: 589318
  PASSED

Test 2: Forward pass shape
  Input shape: torch.Size([8, 30, 6])
  Output shape: torch.Size([8, 6])
  PASSED

Test 3: Patch creation
  Input shape: torch.Size([8, 30, 6])
  Patches shape: torch.Size([8, 6, 30)]
  PASSED

Test 4: Four-parameter model
  Input shape: torch.Size([8, 30, 4])
  Output shape: torch.Size([8, 4])
  PASSED

Test 5: Architecture components
  Patch embedding: Linear
  Positional encoding: PositionalEncoding
  Transformer encoder: TransformerEncoder
  Prediction head: Sequential
  PASSED

Test 6: Different batch sizes
  PASSED for batch sizes: [1, 4, 16, 32]

============================================================
PATCHTST MODEL ARCHITECTURE VERIFIED
============================================================
```

### LSTM Model Verification (UNCHANGED)
```
============================================================
LSTM MODEL ARCHITECTURE VERIFICATION (UNCHANGED)
============================================================

Test 1: Model initialization
  Input size: 6
  Hidden size: 64
  Num layers: 2
  Dropout: 0.2
  Output size: 6
  Total parameters: 52102
  PASSED

Test 2: Forward pass shape
  Input shape: torch.Size([8, 30, 6])
  Output shape: torch.Size([8, 6])
  PASSED

============================================================
LSTM MODEL ARCHITECTURE UNCHANGED
============================================================
```

## Training Configuration

### Default PatchTSTTrainingConfig
```python
PatchTSTTrainingConfig(
    model_name: str = "patchtst_water_quality",
    input_size: int = 6,
    context_length: int = 30,
    patch_length: int = 5,
    stride: int = 5,
    d_model: int = 64,
    num_heads: int = 4,
    num_layers: int = 2,
    dropout: float = 0.1,
    output_size: int = 6,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    num_epochs: int = 100,
    early_stopping_patience: int = 10,
    random_seed: int = 42,
    checkpoint_dir: str = "artifacts/checkpoints",
    device: str = "auto",
    four_param_mode: bool = False,
    parameters: tuple[str, ...] | None = None,
)
```

### CLI Usage Examples

**Four-parameter development mode:**
```bash
python -m ml.training.train_patchtst --parameters pH TDS turbidity temperature
```

**Six-parameter mode (explicit):**
```bash
python -m ml.training.train_patchtst --parameters pH TDS turbidity temperature EC DO
```

**Default six-parameter mode:**
```bash
python -m ml.training.train_patchtst
```

**Custom hyperparameters:**
```bash
python -m ml.training.train_patchtst \
    --patch-length 4 \
    --stride 4 \
    --d-model 128 \
    --num-heads 8 \
    --num-layers 3 \
    --epochs 100 \
    --batch-size 64
```

## Checkpoint Location

- **Default**: `artifacts/checkpoints/patchtst_water_quality_best.pt`
- **Last checkpoint**: `artifacts/checkpoints/patchtst_water_quality_last.pt`

### Checkpoint Contents
```python
{
    "epoch": int,
    "model_state_dict": dict,
    "optimizer_state_dict": dict,
    "val_loss": float,
    "config": {
        "input_size": int,
        "context_length": int,
        "patch_length": int,
        "stride": int,
        "d_model": int,
        "num_heads": int,
        "num_layers": int,
        "dropout": float,
        "output_size": int,
    },
}
```

## EC and DO Handling

### Six-Parameter Mode
- **Status**: Protected against NaN data
- **Behavior**: Raises ValueError if EC/DO contain NaN
- **Error Message**: "Six-parameter PatchTST training requires valid EC and DO data. No fabricated values will be used."
- **Check**: Validates X_train, y_train, X_val, y_val, X_test, y_test

### Four-Parameter Development Mode
- **Status**: Allowed to continue with NaN data
- **Configuration**: Activated via `four_param_mode=True` or `--parameters pH TDS turbidity temperature`
- **Behavior**: Does not check for NaN (since EC/DO are not in parameter set)

## Important Notes

### EC and DO Handling
- **EC and DO are NEVER fabricated** - they remain unavailable in the development dataset
- The data pipeline correctly identifies EC/DO as unavailable columns
- Inverse transformation preserves NaN for unavailable parameters
- Four-parameter mode explicitly handles development without EC/DO sensors

### Data Not Claimed as Real
- The implementation uses synthetic DEMO/TEST data from `data/demo_water_quality.csv`
- This data is clearly labeled as synthetic and not real sensor measurements
- No accuracy claims are made until the model is evaluated on real data

### Android Integration
- **NOT MODIFIED** - Android application was not touched as requested
- All work was focused on the backend PatchTST implementation

### LSTM Model
- **NOT MODIFIED** - LSTM implementation remains unchanged
- LSTM architecture verified: 52,102 parameters, (batch, 30, 6) â†’ (batch, 6)
- LSTM files not modified during PatchTST implementation

### What Was NOT Implemented
- âŒ TimeMixer
- âŒ Adaptive ensemble
- âŒ FastAPI forecast endpoint
- âŒ ESP32 integration
- âŒ Model comparison (LSTM vs PatchTST)

## Comparison: LSTM vs PatchTST

| Feature | LSTM | PatchTST |
|---------|------|----------|
| Architecture | Recurrent (LSTM) | Transformer |
| Parameters | 52,102 | 589,318 |
| Input Processing | Sequential | Patch-based |
| Attention Mechanism | No | Yes (Multi-head) |
| Patch Length | N/A | 5 (configurable) |
| Stride | N/A | 5 (configurable) |
| Hidden Dimension | 64 | 64 (d_model) |
| Num Layers | 2 | 2 |
| Dropout | 0.2 | 0.1 |
| Output Shape | (batch, 6) | (batch, 6) |

## Remaining Limitations

1. **scikit-learn dependency**: Cannot install due to disk space constraints, preventing full data pipeline integration tests
2. **Full test suite**: Cannot run end-to-end training tests due to scikit-learn dependency
3. **Real data evaluation**: Cannot test actual training with real water quality data due to dependency constraints
4. **Performance comparison**: Cannot compare LSTM vs PatchTST performance without real training runs

## Next Steps

1. **Resolve Disk Space**: Free up disk space to install scikit-learn and scipy
2. **Run Full Training**: Execute complete training pipeline with real data
3. **Evaluate Performance**: Calculate real MAE/RMSE metrics on test data
4. **Compare Models**: Benchmark LSTM vs PatchTST performance
5. **Hyperparameter Tuning**: Optimize PatchTST hyperparameters (patch_length, stride, d_model, etc.)

## Summary

The PatchTST forecasting component has been successfully implemented with:

- âœ… Correct Transformer-based architecture (not simplified MLP)
- âœ… Patch-based time series processing
- âœ… Configurable training pipeline with early stopping
- âœ… Prediction and evaluation functions
- âœ… Four-parameter development mode support
- âœ… Comprehensive unit tests (21/21 passed)
- âœ… Compatible with existing data pipeline
- âœ… Proper EC/DO handling (never fabricated)
- âœ… LSTM model remains unchanged
- âœ… Android project not modified

The implementation is ready for use once the scikit-learn dependency is resolved. The PatchTST model follows the paper's architecture with patching, positional encoding, and transformer encoder, providing a modern alternative to the LSTM baseline.
