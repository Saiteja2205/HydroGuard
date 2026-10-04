"""Prediction module for LSTM water quality forecasting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from ml.data import run_pipeline, PipelineConfig, PipelineResult
from ml.models.lstm_model import LSTMModel
from ml.training.train_lstm import TrainingConfig, load_checkpoint


def load_model_for_prediction(
    checkpoint_path: Path,
    device: str = "auto",
) -> tuple[LSTMModel, dict[str, Any]]:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)
    
    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = checkpoint["config"]
    
    model = LSTMModel(
        input_size=config["input_size"],
        hidden_size=config["hidden_size"],
        num_layers=config["num_layers"],
        dropout=config["dropout"],
        output_size=config["output_size"],
    ).to(device)
    
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    return model, checkpoint


def predict(
    model: nn.Module,
    X: np.ndarray,
    device: torch.device,
) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        X_tensor = torch.from_numpy(X).float().to(device)
        predictions = model(X_tensor)
        return predictions.cpu().numpy()


def predict_with_inverse_transform(
    model: nn.Module,
    X: np.ndarray,
    pipeline_result: PipelineResult,
    device: torch.device,
) -> np.ndarray:
    scaled_predictions = predict(model, X, device)
    physical_predictions = pipeline_result.inverse_transform_predictions(scaled_predictions)
    return physical_predictions


def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, float]:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    
    mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    
    if mask.sum() == 0:
        return {"mae": float("nan"), "rmse": float("nan")}
    
    y_true_valid = y_true[mask]
    y_pred_valid = y_pred[mask]
    
    mae = float(np.mean(np.abs(y_true_valid - y_pred_valid)))
    rmse = float(np.sqrt(np.mean((y_true_valid - y_pred_valid) ** 2)))
    
    return {"mae": mae, "rmse": rmse}


def evaluate_on_test(
    checkpoint_path: Path,
    data_source: str | Path,
    pipeline_config: PipelineConfig | None = None,
    device: str = "auto",
) -> dict[str, Any]:
    model, checkpoint = load_model_for_prediction(checkpoint_path, device)
    device_obj = next(model.parameters()).device
    
    pipeline_config = pipeline_config or PipelineConfig()
    
    config_dict = checkpoint["config"]
    if config_dict["output_size"] == 4:
        pipeline_config.parameters = ("pH", "TDS", "turbidity", "temperature")
    
    result = run_pipeline(data_source, pipeline_config)
    
    X_test = result.X_test
    y_test = result.y_test
    
    if X_test.shape[0] == 0:
        return {
            "error": "Test set is empty",
            "n_test_windows": 0,
            "metrics": {"mae": float("nan"), "rmse": float("nan")},
        }
    
    scaled_predictions = predict(model, X_test, device_obj)
    physical_predictions = result.inverse_transform_predictions(scaled_predictions)
    physical_test = result.inverse_transform_predictions(y_test)
    
    metrics = calculate_metrics(physical_test, physical_predictions)
    
    return {
        "n_test_samples": X_test.shape[0],
        "input_shape": X_test.shape,
        "output_shape": physical_predictions.shape,
        "metrics": metrics,
        "available_columns": result.diagnostics["available_columns"],
        "unavailable_columns": result.diagnostics["unavailable_columns"],
    }


if __name__ == "__main__":
    checkpoint_path = Path("artifacts/checkpoints/lstm_water_quality_best.pt")
    
    if not checkpoint_path.exists():
        print(f"Checkpoint not found: {checkpoint_path}")
        print("Please train the model first using ml/training/train_lstm.py")
    else:
        results = evaluate_on_test(
            checkpoint_path=checkpoint_path,
            data_source="data/demo_water_quality.csv",
        )
        
        print("Test set evaluation results:")
        print(f"  Test samples: {results.get('n_test_samples', 0)}")
        print(f"  Input shape: {results.get('input_shape', 'N/A')}")
        print(f"  Output shape: {results.get('output_shape', 'N/A')}")
        print(f"  MAE: {results['metrics']['mae']:.6f}")
        print(f"  RMSE: {results['metrics']['rmse']:.6f}")
        print(f"  Available columns: {results.get('available_columns', [])}")
        print(f"  Unavailable columns: {results.get('unavailable_columns', [])}")
