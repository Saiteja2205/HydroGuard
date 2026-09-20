"""
Development-only end-to-end ML demonstration script.

Trains LSTM, PatchTST, and TimeMixer models on synthetic demo data.

IMPORTANT:
- This is NOT real sensor data
- Do not present metrics as real-world accuracy
- Synthetic data used only for pipeline validation
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Use four-parameter mode for development (avoid EC/DO issues)
PARAMETERS = ("pH", "TDS", "turbidity", "temperature")
INPUT_SIZE = 4
OUTPUT_SIZE = 4
WINDOW_SIZE = 30


def load_demo_data(data_path: str) -> np.ndarray:
    """Load and preprocess demo data without sklearn."""
    import csv
    
    data = []
    with open(data_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append([
                float(row['pH']),
                float(row['TDS']),
                float(row['turbidity']),
                float(row['temperature']),
            ])
    
    return np.array(data, dtype=np.float32)


def prepare_data(data: np.ndarray) -> tuple:
    """Prepare sliding windows for training."""
    sequences = []
    targets = []
    
    for i in range(len(data) - WINDOW_SIZE):
        sequences.append(data[i:i + WINDOW_SIZE])
        targets.append(data[i + WINDOW_SIZE])
    
    X = np.array(sequences)
    y = np.array(targets)
    
    # Train/val/test split (70/15/15)
    n = len(X)
    n_train = int(n * 0.7)
    n_val = int(n * 0.85)
    
    X_train, y_train = X[:n_train], y[:n_train]
    X_val, y_val = X[n_train:n_val], y[n_train:n_val]
    X_test, y_test = X[n_val:], y[n_val:]
    
    # Simple normalization (z-score) - normalize X and y separately
    X_mean = X_train.mean(axis=0)
    X_std = X_train.std(axis=0)
    X_std[X_std == 0] = 1.0
    
    y_mean = y_train.mean(axis=0)
    y_std = y_train.std(axis=0)
    y_std[y_std == 0] = 1.0
    
    X_train = (X_train - X_mean) / X_std
    X_val = (X_val - X_mean) / X_std
    X_test = (X_test - X_mean) / X_std
    
    y_train = (y_train - y_mean) / y_std
    y_val = (y_val - y_mean) / y_std
    y_test = (y_test - y_mean) / y_std
    
    return (X_train, y_train, X_val, y_val, X_test, y_test), (X_mean, X_std, y_mean, y_std)


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Calculate MAE and RMSE."""
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    return {"mae": mae, "rmse": rmse}


def train_lstm(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    checkpoint_path: Path,
    num_epochs: int = 50,
    batch_size: int = 16,
    learning_rate: float = 0.001,
) -> dict:
    """Train LSTM model."""
    from ml.models.lstm_model import LSTMModel
    
    model = LSTMModel(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    
    train_dataset = TensorDataset(
        torch.from_numpy(X_train).float(),
        torch.from_numpy(y_train).float(),
    )
    val_dataset = TensorDataset(
        torch.from_numpy(X_val).float(),
        torch.from_numpy(y_val).float(),
    )
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0
    
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
        val_loss /= len(val_loader)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'config': {
                    'input_size': INPUT_SIZE,
                    'output_size': OUTPUT_SIZE,
                },
            }, checkpoint_path)
            patience_counter = 0
        else:
            patience_counter += 1
        
        if patience_counter >= patience:
            break
    
    return {"best_val_loss": best_val_loss, "train_time": 0.0}


def train_patchtst(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    checkpoint_path: Path,
    num_epochs: int = 50,
    batch_size: int = 16,
    learning_rate: float = 0.001,
) -> dict:
    """Train PatchTST model."""
    from ml.models.patchtst_model import PatchTST
    
    model = PatchTST(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    
    train_dataset = TensorDataset(
        torch.from_numpy(X_train).float(),
        torch.from_numpy(y_train).float(),
    )
    val_dataset = TensorDataset(
        torch.from_numpy(X_val).float(),
        torch.from_numpy(y_val).float(),
    )
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0
    
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
        val_loss /= len(val_loader)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'config': {
                    'input_size': INPUT_SIZE,
                    'output_size': OUTPUT_SIZE,
                },
            }, checkpoint_path)
            patience_counter = 0
        else:
            patience_counter += 1
        
        if patience_counter >= patience:
            break
    
    return {"best_val_loss": best_val_loss, "train_time": 0.0}


def train_timemixer(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    checkpoint_path: Path,
    num_epochs: int = 50,
    batch_size: int = 16,
    learning_rate: float = 0.001,
) -> dict:
    """Train TimeMixer model."""
    from ml.models.timemixer_model import TimeMixer
    
    model = TimeMixer(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    
    train_dataset = TensorDataset(
        torch.from_numpy(X_train).float(),
        torch.from_numpy(y_train).float(),
    )
    val_dataset = TensorDataset(
        torch.from_numpy(X_val).float(),
        torch.from_numpy(y_val).float(),
    )
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0
    
    for epoch in range(num_epochs):
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
        val_loss /= len(val_loader)
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': val_loss,
                'config': {
                    'input_size': INPUT_SIZE,
                    'output_size': OUTPUT_SIZE,
                },
            }, checkpoint_path)
            patience_counter = 0
        else:
            patience_counter += 1
        
        if patience_counter >= patience:
            break
    
    return {"best_val_loss": best_val_loss, "train_time": 0.0}


def evaluate_model(
    model: nn.Module,
    X_test: np.ndarray,
    y_test: np.ndarray,
    y_mean: np.ndarray,
    y_std: np.ndarray,
) -> dict:
    """Evaluate model on test set."""
    model.eval()
    with torch.no_grad():
        predictions = model(torch.from_numpy(X_test).float())
        predictions = predictions.numpy()
    
    # Inverse transform predictions
    predictions = predictions * y_std + y_mean
    y_test = y_test * y_std + y_mean
    
    metrics = calculate_metrics(y_test, predictions)
    return metrics


def main() -> None:
    print("="*70)
    print("HYDROGUARD ML DEMONSTRATION - END-TO-END TRAINING")
    print("="*70)
    print("\nIMPORTANT NOTICE:")
    print("- This is synthetic development data")
    print("- Do NOT present metrics as real-world accuracy")
    print("- Used only for pipeline validation")
    print("- Using four-parameter mode (pH, TDS, turbidity, temperature)")
    print("="*70)

    # Configuration
    data_source = "data/demo_water_quality_200days.csv"
    checkpoint_dir = "artifacts/checkpoints"
    results_dir = "artifacts/results"
    num_epochs = 50
    batch_size = 16
    learning_rate = 0.001

    # Create directories
    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # Check data file
    data_path = Path(data_source)
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}")
        return

    print(f"\n1. Loading data from: {data_path}")
    data = load_demo_data(data_source)
    print(f"   Loaded {len(data)} samples")

    print(f"\n2. Preparing data (window_size={WINDOW_SIZE})")
    (X_train, y_train, X_val, y_val, X_test, y_test), (X_mean, X_std, y_mean, y_std) = prepare_data(data)
    print(f"   Training samples: {len(X_train)}")
    print(f"   Validation samples: {len(X_val)}")
    print(f"   Test samples: {len(X_test)}")

    # Train models
    all_metrics = {}

    # LSTM
    print("\n" + "="*70)
    print("3. Training LSTM Model")
    print("="*70)
    lstm_start = time.time()
    lstm_checkpoint = Path(checkpoint_dir) / "lstm_water_quality_best.pt"
    try:
        lstm_metrics = train_lstm(X_train, y_train, X_val, y_val, lstm_checkpoint, num_epochs, batch_size, learning_rate)
        lstm_time = time.time() - lstm_start
        print(f"   LSTM training completed in {lstm_time:.2f}s")
        print(f"   Best validation loss: {lstm_metrics['best_val_loss']:.6f}")
        
        # Evaluate
        from ml.models.lstm_model import LSTMModel
        lstm_model = LSTMModel(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
        checkpoint = torch.load(lstm_checkpoint, map_location='cpu')
        lstm_model.load_state_dict(checkpoint['model_state_dict'])
        lstm_eval = evaluate_model(lstm_model, X_test, y_test, y_mean, y_std)
        all_metrics["LSTM"] = {
            "MAE": lstm_eval,
            "RMSE": {"rmse": lstm_eval["rmse"]},
            "train_time_seconds": lstm_time,
            "best_val_loss": lstm_metrics['best_val_loss'],
        }
        print(f"   Test MAE: {lstm_eval['mae']:.6f}")
        print(f"   Test RMSE: {lstm_eval['rmse']:.6f}")
    except Exception as e:
        print(f"   ERROR training LSTM: {e}")
        all_metrics["LSTM"] = {"error": str(e)}

    # PatchTST
    print("\n" + "="*70)
    print("4. Training PatchTST Model")
    print("="*70)
    patchtst_start = time.time()
    patchtst_checkpoint = Path(checkpoint_dir) / "patchtst_water_quality_best.pt"
    try:
        patchtst_metrics = train_patchtst(X_train, y_train, X_val, y_val, patchtst_checkpoint, num_epochs, batch_size, learning_rate)
        patchtst_time = time.time() - patchtst_start
        print(f"   PatchTST training completed in {patchtst_time:.2f}s")
        print(f"   Best validation loss: {patchtst_metrics['best_val_loss']:.6f}")
        
        # Evaluate
        from ml.models.patchtst_model import PatchTST
        patchtst_model = PatchTST(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
        checkpoint = torch.load(patchtst_checkpoint, map_location='cpu')
        patchtst_model.load_state_dict(checkpoint['model_state_dict'])
        patchtst_eval = evaluate_model(patchtst_model, X_test, y_test, y_mean, y_std)
        all_metrics["PatchTST"] = {
            "MAE": patchtst_eval,
            "RMSE": {"rmse": patchtst_eval["rmse"]},
            "train_time_seconds": patchtst_time,
            "best_val_loss": patchtst_metrics['best_val_loss'],
        }
        print(f"   Test MAE: {patchtst_eval['mae']:.6f}")
        print(f"   Test RMSE: {patchtst_eval['rmse']:.6f}")
    except Exception as e:
        print(f"   ERROR training PatchTST: {e}")
        all_metrics["PatchTST"] = {"error": str(e)}

    # TimeMixer
    print("\n" + "="*70)
    print("5. Training TimeMixer Model")
    print("="*70)
    timemixer_start = time.time()
    timemixer_checkpoint = Path(checkpoint_dir) / "timemixer_water_quality_best.pt"
    try:
        timemixer_metrics = train_timemixer(X_train, y_train, X_val, y_val, timemixer_checkpoint, num_epochs, batch_size, learning_rate)
        timemixer_time = time.time() - timemixer_start
        print(f"   TimeMixer training completed in {timemixer_time:.2f}s")
        print(f"   Best validation loss: {timemixer_metrics['best_val_loss']:.6f}")
        
        # Evaluate
        from ml.models.timemixer_model import TimeMixer
        timemixer_model = TimeMixer(input_size=INPUT_SIZE, output_size=OUTPUT_SIZE)
        checkpoint = torch.load(timemixer_checkpoint, map_location='cpu')
        timemixer_model.load_state_dict(checkpoint['model_state_dict'])
        timemixer_eval = evaluate_model(timemixer_model, X_test, y_test, y_mean, y_std)
        all_metrics["TimeMixer"] = {
            "MAE": timemixer_eval,
            "RMSE": {"rmse": timemixer_eval["rmse"]},
            "train_time_seconds": timemixer_time,
            "best_val_loss": timemixer_metrics['best_val_loss'],
        }
        print(f"   Test MAE: {timemixer_eval['mae']:.6f}")
        print(f"   Test RMSE: {timemixer_eval['rmse']:.6f}")
    except Exception as e:
        print(f"   ERROR training TimeMixer: {e}")
        all_metrics["TimeMixer"] = {"error": str(e)}

    # Save metrics
    print("\n" + "="*70)
    print("6. Saving Evaluation Results")
    print("="*70)
    
    metrics_path = Path(results_dir) / "model_metrics.json"
    metrics_with_metadata = {
        "data_mode": "synthetic_development",
        "parameters": list(PARAMETERS),
        "note": "Synthetic data used only for pipeline validation. Do not use for real-world accuracy claims.",
        "epochs": num_epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "window_size": WINDOW_SIZE,
        "models": all_metrics,
    }
    
    with open(metrics_path, "w") as f:
        json.dump(metrics_with_metadata, f, indent=2)
    
    print(f"   Metrics saved to: {metrics_path}")

    # Summary
    print("\n" + "="*70)
    print("TRAINING SUMMARY")
    print("="*70)
    print(f"Mode: Four-parameter ({', '.join(PARAMETERS)})")
    print(f"Epochs per model: {num_epochs}")
    print(f"Batch size: {batch_size}")
    print(f"Learning rate: {learning_rate}")
    
    print("\nCheckpoints generated:")
    for model_name in ["LSTM", "PatchTST", "TimeMixer"]:
        checkpoint_name = model_name.lower() + "_water_quality_best.pt"
        checkpoint_path = Path(checkpoint_dir) / checkpoint_name
        if checkpoint_path.exists():
            print(f"  [OK] {checkpoint_path}")
        else:
            print(f"  [FAIL] {checkpoint_path}")
    
    print("\n" + "="*70)
    print("IMPORTANT DISCLAIMER")
    print("="*70)
    print("This demonstration used SYNTHETIC data.")
    print("Do NOT present these metrics as real-world accuracy.")
    print("Metrics are for pipeline validation only.")
    print("="*70)


if __name__ == "__main__":
    main()
