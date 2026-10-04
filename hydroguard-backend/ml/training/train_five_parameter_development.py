"""Train the active five-parameter models on an explicitly simulated dataset."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from ml.data.validator import PARAMETERS
from ml.models.lstm_model import LSTMModel
from ml.models.patchtst_model import PatchTST
from ml.models.timemixer_model import TimeMixer
from ml.ensemble.weighting import calculate_parameter_weights

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "development_water_quality_200_observations.csv"
OUT = ROOT / "artifacts" / "checkpoints"
RESULTS = ROOT / "artifacts" / "results" / "five_parameter_evaluation.json"
WINDOW = 30
EPOCHS = 40


def windows(values: np.ndarray, targets: range) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for target in targets:
        xs.append(values[target-WINDOW:target])
        ys.append(values[target])
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    error = predicted - actual
    result = {}
    for i, name in enumerate(PARAMETERS):
        truth, residual = actual[:, i], error[:, i]
        denominator = np.maximum(np.abs(truth), 1e-8)
        result[name] = {
            "MAE": float(np.mean(np.abs(residual))),
            "RMSE": float(np.sqrt(np.mean(residual ** 2))),
            "MAPE": float(np.mean(np.abs(residual) / denominator) * 100),
        }
    return result


def main() -> None:
    torch.manual_seed(42)
    np.random.seed(42)
    frame = pd.read_csv(DATA, comment="#")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if len(frame) != 200 or frame.timestamp.duplicated().any():
        raise ValueError("Expected exactly 200 chronologically ordered observations.")
    # Causal forward-fill only; this never uses a later observation to fill an earlier gap.
    frame[list(PARAMETERS)] = frame[list(PARAMETERS)].apply(pd.to_numeric, errors="coerce").ffill()
    if frame[list(PARAMETERS)].isna().any().any():
        raise ValueError("An initial missing feature has no earlier value for causal filling.")
    data = frame[list(PARAMETERS)].to_numpy(dtype=np.float64)
    if not np.isfinite(data).all():
        raise ValueError("Five-parameter dataset contains a non-finite value.")
    train_end, val_end = int(len(data)*.70), int(len(data)*.85)
    mean, std = data[:train_end].mean(axis=0), data[:train_end].std(axis=0)
    std[std == 0] = 1.0
    scaled = (data - mean) / std
    Xtr, ytr = windows(scaled, range(WINDOW, train_end))
    Xv, yv = windows(scaled, range(train_end, val_end))
    Xt, yt = windows(scaled, range(val_end, len(data)))
    device = torch.device("cpu")
    OUT.mkdir(parents=True, exist_ok=True)
    all_scaled_preds, val_scaled_preds = {}, {}
    training_results = {}
    model_defs = {
        "LSTM": (LSTMModel(input_size=5, output_size=5), "lstm_water_quality_5param_v1.pt"),
        "PatchTST": (PatchTST(input_size=5, context_length=WINDOW, output_size=5), "patchtst_water_quality_5param_v1.pt"),
        "TimeMixer": (TimeMixer(input_size=5, context_length=WINDOW, output_size=5), "timemixer_water_quality_5param_v1.pt"),
    }
    timestamp = datetime.now(timezone.utc).isoformat()
    for name, (model, filename) in model_defs.items():
        model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = nn.MSELoss()
        tx, ty = torch.from_numpy(Xtr), torch.from_numpy(ytr)
        best_loss, best_state = float("inf"), None
        for _ in range(EPOCHS):
            model.train()
            order = torch.randperm(len(tx))
            for ids in order.split(16):
                optimizer.zero_grad()
                loss = loss_fn(model(tx[ids]), ty[ids])
                loss.backward()
                optimizer.step()
            model.eval()
            with torch.no_grad():
                val_loss = float(loss_fn(model(torch.from_numpy(Xv)), torch.from_numpy(yv)))
            if val_loss < best_loss:
                best_loss, best_state = val_loss, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            val_scaled_preds[name] = model(torch.from_numpy(Xv)).numpy()
            all_scaled_preds[name] = model(torch.from_numpy(Xt)).numpy()
        model_config = {"input_size": 5, "output_size": 5}
        if name == "LSTM":
            model_config.update(hidden_size=64, num_layers=2, dropout=0.2)
        elif name == "PatchTST":
            model_config.update(context_length=WINDOW, patch_length=5, stride=5, d_model=64, num_heads=4, num_layers=2, dropout=0.1)
        else:
            model_config.update(context_length=WINDOW, hidden_size=64, num_scales=3, num_mixing_layers=2, dropout=0.1)
        training_results[name] = {
            "status": "trained",
            "best_validation_mse_scaled": best_loss,
            "input_shape": [None, WINDOW, 5],
            "output_shape": [None, 5],
            "checkpoint": str(OUT / filename),
        }
        checkpoint = {
            "model": name, "model_version": "five-param-v1", "feature_count": 5,
            "parameters": list(PARAMETERS), "dataset_size": 200,
            "dataset_source": "SIMULATED/DEVELOPMENT", "real_sensor_data": False,
            "training_timestamp": timestamp, "train_observations": train_end,
            "validation_observations": val_end-train_end, "test_observations": len(data)-val_end,
            "window_size": WINDOW, "scaler_mean": mean.tolist(), "scaler_std": std.tolist(),
            "config": model_config,
            "model_state_dict": best_state, "best_validation_mse_scaled": best_loss,
        }
        torch.save(checkpoint, OUT / filename)
    actual = data[val_end:]
    pred = {name: val * std + mean for name, val in all_scaled_preds.items()}
    val_actual = data[train_end:val_end]
    val_physical = {name: val * std + mean for name, val in val_scaled_preds.items()}
    val_mae = {name: np.mean(np.abs(val_physical[name] - val_actual), axis=0) for name in model_defs}
    err_map = {model: {p: float(val_mae[model][i]) for i, p in enumerate(PARAMETERS)} for model in model_defs}
    model_errors = {model: {p: float(np.mean(np.abs(val_physical[model][:, i] - val_actual[:, i]))) for i, p in enumerate(PARAMETERS)} for model in model_defs}
    weights = calculate_parameter_weights(model_errors)
    test_model_metrics = {name: metrics(actual, pred[name]) for name in model_defs}
    ensemble = np.column_stack([
        sum(pred[m][:, i] * weights[p][m] for m in model_defs)
        for i, p in enumerate(PARAMETERS)
    ])
    report = {
        "model_version": "five-param-v1", "dataset_size": len(data),
        "dataset_source": "SIMULATED/DEVELOPMENT", "real_sensor_data": False,
        "parameters": list(PARAMETERS), "split": {"train": train_end, "validation": val_end-train_end, "test": len(data)-val_end},
        "window_size": WINDOW, "training_timestamp": timestamp,
        "training_results": training_results,
        "validation_metrics_by_model": {m: metrics(val_actual, val_physical[m]) for m in model_defs},
        "test_metrics_by_model": test_model_metrics,
        "adaptive_ensemble_weights_from_validation": weights,
        "adaptive_ensemble_test_metrics": metrics(actual, ensemble),
        "checkpoints": {m: str(OUT / filename) for m, (_, filename) in model_defs.items()},
        "note": "Development/simulated data only; not evidence of real-world accuracy.",
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
