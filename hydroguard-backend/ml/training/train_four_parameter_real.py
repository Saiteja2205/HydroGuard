"""Train and evaluate 4-parameter water quality models on real ThingSpeak sensor observations.

Features (4 core parameters):
1. pH
2. TDS
3. Turbidity
4. Temperature

No optical_colour_index is used or invented. Scalers are fit exclusively on the
chronological training split to prevent future data leakage. Performance is
rigorously compared against a persistence baseline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch
from torch import nn

from ml.models.lstm_model import LSTMModel

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "real_thingspeak_observations_122.csv"
META_PATH = ROOT / "data" / "real_thingspeak_observations_122.metadata.json"
OUT_DIR = ROOT / "artifacts" / "checkpoints"
RESULTS_PATH = ROOT / "artifacts" / "results" / "real_thingspeak_evaluation.json"

PARAMETERS = ("pH", "TDS", "turbidity", "temperature")
WINDOW = 5
EPOCHS = 50


def create_windows(values: np.ndarray, window_size: int, targets: range) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for target in targets:
        xs.append(values[target - window_size:target])
        ys.append(values[target])
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def calculate_parameter_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, dict[str, float]]:
    error = predicted - actual
    result = {}
    for i, name in enumerate(PARAMETERS):
        truth, residual = actual[:, i], error[:, i]
        denom = np.maximum(np.abs(truth), 1e-6)
        result[name] = {
            "MAE": float(np.mean(np.abs(residual))),
            "RMSE": float(np.sqrt(np.mean(residual ** 2))),
            "MAPE": float(np.mean(np.abs(residual) / denom) * 100),
        }
    return result


def main() -> None:
    torch.manual_seed(42)
    np.random.seed(42)

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Real sensor dataset not found: {DATA_PATH}")

    frame = pd.read_csv(DATA_PATH)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    n_rows = len(frame)
    if n_rows < 30:
        raise ValueError(f"Insufficient observations ({n_rows}) to construct train/val/test splits.")

    raw_data = frame[list(PARAMETERS)].to_numpy(dtype=np.float64)
    if not np.isfinite(raw_data).all():
        raise ValueError("Real sensor data contains non-finite values.")

    # Chronological 70% / 15% / 15% split
    train_end = int(n_rows * 0.70)
    val_end = int(n_rows * 0.85)

    # Scaler fit STRICTLY on training split
    train_slice = raw_data[:train_end]
    mean = train_slice.mean(axis=0)
    std = train_slice.std(axis=0)
    std[std == 0] = 1.0

    scaled = (raw_data - mean) / std

    X_train, y_train = create_windows(scaled, WINDOW, range(WINDOW, train_end))
    X_val, y_val = create_windows(scaled, WINDOW, range(train_end, val_end))
    X_test, y_test = create_windows(scaled, WINDOW, range(val_end, n_rows))

    # Persistence Baseline: y_hat = last step in the input window
    pers_val_scaled = X_val[:, -1, :]
    pers_test_scaled = X_test[:, -1, :]

    val_actual = raw_data[train_end:val_end]
    test_actual = raw_data[val_end:]

    pers_val_pred = pers_val_scaled * std + mean
    pers_test_pred = pers_test_scaled * std + mean

    persistence_val_metrics = calculate_parameter_metrics(val_actual, pers_val_pred)
    persistence_test_metrics = calculate_parameter_metrics(test_actual, pers_test_pred)

    # Train a 4-feature LSTM
    device = torch.device("cpu")
    model = LSTMModel(input_size=4, hidden_size=32, num_layers=1, output_size=4, dropout=0.0)
    model.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
    loss_fn = nn.MSELoss()

    tx = torch.from_numpy(X_train)
    ty = torch.from_numpy(y_train)
    vx = torch.from_numpy(X_val)
    vy = torch.from_numpy(y_val)

    best_loss = float("inf")
    best_state = None

    for _ in range(EPOCHS):
        model.train()
        order = torch.randperm(len(tx))
        for ids in order.split(16):
            optimizer.zero_grad()
            out = model(tx[ids])
            loss = loss_fn(out, ty[ids])
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            vloss = float(loss_fn(model(vx), vy))
        if vloss < best_loss:
            best_loss = vloss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    model.eval()

    with torch.no_grad():
        lstm_val_scaled = model(vx).numpy()
        lstm_test_scaled = model(torch.from_numpy(X_test)).numpy()

    lstm_val_pred = lstm_val_scaled * std + mean
    lstm_test_pred = lstm_test_scaled * std + mean

    lstm_val_metrics = calculate_parameter_metrics(val_actual, lstm_val_pred)
    lstm_test_metrics = calculate_parameter_metrics(test_actual, lstm_test_pred)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = OUT_DIR / "lstm_water_quality_4param_real_v1.pt"

    checkpoint = {
        "model": "LSTM",
        "model_version": "four-param-real-v1",
        "feature_count": 4,
        "parameters": list(PARAMETERS),
        "dataset_size": n_rows,
        "dataset_source": "THINGSPEAK_HARDWARE",
        "real_sensor_data": True,
        "channel_id": 244357,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "train_observations": train_end,
        "validation_observations": val_end - train_end,
        "test_observations": n_rows - val_end,
        "window_size": WINDOW,
        "scaler_mean": mean.tolist(),
        "scaler_std": std.tolist(),
        "config": {
            "input_size": 4,
            "hidden_size": 32,
            "num_layers": 1,
            "output_size": 4,
            "dropout": 0.0,
        },
        "model_state_dict": best_state,
        "best_validation_mse_scaled": best_loss,
    }
    torch.save(checkpoint, ckpt_path)

    report = {
        "model_version": "four-param-real-v1",
        "dataset_size": n_rows,
        "dataset_source": "THINGSPEAK_HARDWARE",
        "channel_id": 244357,
        "real_sensor_data": True,
        "date_range": {
            "start": frame["timestamp"].iloc[0].isoformat(),
            "end": frame["timestamp"].iloc[-1].isoformat(),
        },
        "parameters": list(PARAMETERS),
        "window_size": WINDOW,
        "split": {
            "train": train_end,
            "validation": val_end - train_end,
            "test": n_rows - val_end,
        },
        "training_timestamp": checkpoint["training_timestamp"],
        "checkpoint": str(ckpt_path),
        "persistence_baseline_validation_metrics": persistence_val_metrics,
        "persistence_baseline_test_metrics": persistence_test_metrics,
        "lstm_validation_metrics": lstm_val_metrics,
        "lstm_test_metrics": lstm_test_metrics,
        "limitations": [
            "122 total observations collected in 5 disconnected bench sessions across 7 days.",
            "Contains multiple multi-hour/multi-day gaps (up to 89.3 hours) where the hardware was unpowered.",
            "Data represents short bench calibration tests, not a continuous 24-hour water tank sequence.",
            "Persistence baseline outperforms or matches ML model on test set for stable metrics.",
            "Continuous 24/7 telemetry collection is required before multi-step forecasting can be clinically or operationally deployed."
        ],
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Model saved to {ckpt_path}")
    print(f"Results saved to {RESULTS_PATH}")
    print("\n--- Persistence Baseline Test Metrics ---")
    for p in PARAMETERS:
        m = persistence_test_metrics[p]
        print(f"  {p}: MAE={m['MAE']:.4f}, RMSE={m['RMSE']:.4f}")
    print("\n--- 4-Param Real LSTM Test Metrics ---")
    for p in PARAMETERS:
        m = lstm_test_metrics[p]
        print(f"  {p}: MAE={m['MAE']:.4f}, RMSE={m['RMSE']:.4f}")


if __name__ == "__main__":
    main()
