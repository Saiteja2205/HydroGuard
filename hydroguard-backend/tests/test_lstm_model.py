"""Unit tests for LSTM water quality forecasting model.

Tests use synthetic DEMO/TEST data. These are not real sensor measurements
and must not be reported as a real dataset or model accuracy.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.data.dataset import PipelineConfig, run_pipeline
from ml.models.lstm_model import LSTMModel
from ml.prediction.predict_lstm import (
    calculate_metrics,
    evaluate_on_test,
    load_model_for_prediction,
    predict,
    predict_with_inverse_transform,
)
from ml.training.train_lstm import (
    TrainingConfig,
    TrainingMetrics,
    create_data_loaders,
    get_device,
    load_checkpoint,
    save_checkpoint,
    set_random_seed,
    train_epoch,
    train_lstm,
    validate,
)


def synthetic_series(n_days: int = 40, start: str = "2026-01-01") -> pd.DataFrame:
    """Build a labeled synthetic frame (not real sensor data)."""
    index = pd.date_range(start, periods=n_days, freq="D", tz="UTC")
    day = np.arange(n_days, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "pH": 7.0 + 0.02 * np.sin(day / 5.0),
            "TDS": 180.0 + day,
            "turbidity": 1.2 + 0.01 * day,
            "temperature": 22.0 + 0.05 * np.cos(day / 3.0),
            "optical_colour_index": 0.5 + 0.01 * np.sin(day / 4.0),
        }
    )


def synthetic_five_param_series(n_days: int = 40, start: str = "2026-01-01") -> pd.DataFrame:
    """Build a synthetic frame with only 4 parameters (not real sensor data)."""
    index = pd.date_range(start, periods=n_days, freq="D", tz="UTC")
    day = np.arange(n_days, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "pH": 7.0 + 0.02 * np.sin(day / 5.0),
            "TDS": 180.0 + day,
            "turbidity": 1.2 + 0.01 * day,
            "temperature": 22.0 + 0.05 * np.cos(day / 3.0),
            "optical_colour_index": 0.5 + 0.01 * np.sin(day / 4.0),
        }
    )


class LSTMModelTests(unittest.TestCase):
    def test_model_initialization_default(self) -> None:
        model = LSTMModel()
        self.assertEqual(model.input_size, 5)
        self.assertEqual(model.hidden_size, 64)
        self.assertEqual(model.num_layers, 2)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 5)

    def test_model_initialization_custom(self) -> None:
        model = LSTMModel(input_size=5, hidden_size=32, num_layers=1, dropout=0.1, output_size=5)
        self.assertEqual(model.input_size, 5)
        self.assertEqual(model.hidden_size, 32)
        self.assertEqual(model.num_layers, 1)
        self.assertEqual(model.dropout, 0.1)
        self.assertEqual(model.output_size, 5)

    def test_forward_pass_shape(self) -> None:
        model = LSTMModel()
        batch_size = 8
        X = torch.randn(batch_size, 30, 5)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 5))

    def test_forward_pass_five_param(self) -> None:
        model = LSTMModel(input_size=5, output_size=5)
        batch_size = 8
        X = torch.randn(batch_size, 30, 5)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 5))

    def test_model_parameter_count(self) -> None:
        model = LSTMModel()
        n_params = model.get_num_parameters()
        self.assertGreater(n_params, 0)
        self.assertLess(n_params, 1000000)


class RandomSeedTests(unittest.TestCase):
    def test_random_seed_reproducibility(self) -> None:
        set_random_seed(42)
        model1 = LSTMModel()
        weights1 = [p.clone() for p in model1.parameters()]

        set_random_seed(42)
        model2 = LSTMModel()
        weights2 = [p.clone() for p in model2.parameters()]

        for w1, w2 in zip(weights1, weights2):
            self.assertTrue(torch.allclose(w1, w2))


class DeviceTests(unittest.TestCase):
    def test_get_device_auto_cpu(self) -> None:
        device = get_device("auto")
        self.assertEqual(device.type, "cpu")

    def test_get_device_explicit_cpu(self) -> None:
        device = get_device("cpu")
        self.assertEqual(device.type, "cpu")


class DataLoaderTests(unittest.TestCase):
    def test_data_loader_creation(self) -> None:
        X_train = np.random.randn(100, 30, 5).astype(np.float32)
        y_train = np.random.randn(100, 4).astype(np.float32)
        X_val = np.random.randn(20, 30, 5).astype(np.float32)
        y_val = np.random.randn(20, 4).astype(np.float32)

        train_loader, val_loader = create_data_loaders(X_train, y_train, X_val, y_val, batch_size=8)

        self.assertEqual(len(train_loader), 13)
        self.assertEqual(len(val_loader), 3)

    def test_data_loader_five_param(self) -> None:
        X_train = np.random.randn(100, 30, 5).astype(np.float32)
        y_train = np.random.randn(100, 4).astype(np.float32)
        X_val = np.random.randn(20, 30, 5).astype(np.float32)
        y_val = np.random.randn(20, 4).astype(np.float32)

        train_loader, val_loader = create_data_loaders(X_train, y_train, X_val, y_val, batch_size=8)

        self.assertEqual(len(train_loader), 13)
        self.assertEqual(len(val_loader), 3)


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_save_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "test_checkpoint.pt"
            model = LSTMModel()
            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

            config = TrainingConfig(input_size=6, hidden_size=64, num_layers=2, dropout=0.2, output_size=6)
            save_checkpoint(model, optimizer, epoch=5, val_loss=0.123, config=config, checkpoint_path=checkpoint_path)

            self.assertTrue(checkpoint_path.exists())

            new_model = LSTMModel()
            new_optimizer = torch.optim.Adam(new_model.parameters(), lr=0.001)
            checkpoint = load_checkpoint(checkpoint_path, new_model, new_optimizer)

            self.assertEqual(checkpoint["epoch"], 5)
            self.assertAlmostEqual(checkpoint["val_loss"], 0.123, places=6)

            for p1, p2 in zip(model.parameters(), new_model.parameters()):
                self.assertTrue(torch.allclose(p1, p2))


class PredictionTests(unittest.TestCase):
    def test_predict_shape(self) -> None:
        model = LSTMModel()
        model.eval()
        X = np.random.randn(10, 30, 5).astype(np.float32)
        device = torch.device("cpu")

        predictions = predict(model, X, device)
        self.assertEqual(predictions.shape, (10, 5))

    def test_predict_five_param_shape(self) -> None:
        model = LSTMModel(input_size=5, output_size=5)
        model.eval()
        X = np.random.randn(10, 30, 5).astype(np.float32)
        device = torch.device("cpu")

        predictions = predict(model, X, device)
        self.assertEqual(predictions.shape, (10, 5))

    def test_calculate_metrics(self) -> None:
        y_true = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        y_pred = np.array([[1.1, 2.1, 3.1], [4.1, 5.1, 6.1]])

        metrics = calculate_metrics(y_true, y_pred)
        self.assertAlmostEqual(metrics["mae"], 0.1, places=6)
        self.assertGreater(metrics["rmse"], 0.0)

    def test_calculate_metrics_with_nan(self) -> None:
        y_true = np.array([[1.0, 2.0, np.nan], [4.0, 5.0, 6.0]])
        y_pred = np.array([[1.1, 2.1, 3.1], [4.1, 5.1, 6.1]])

        metrics = calculate_metrics(y_true, y_pred)
        self.assertAlmostEqual(metrics["mae"], 0.1, places=6)


class IntegrationTests(unittest.TestCase):
    def test_train_rejects_parameters_outside_product_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "test_data.csv"
            synthetic_series(50).to_csv(csv_path, index=False)

            config = TrainingConfig(
                random_seed=42,
                num_epochs=5,
                checkpoint_dir=str(tmp_path / "checkpoints"),
                parameters=("pH", "TDS", "turbidity", "temperature", "experimental"),
            )
            with self.assertRaisesRegex(ValueError, "restricted"):
                train_lstm(csv_path, config)

    def test_train_lstm_with_five_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "test_data.csv"
            synthetic_five_param_series(50).to_csv(csv_path, index=False)

            config = TrainingConfig(
                random_seed=42,
                num_epochs=5,
                checkpoint_dir=str(tmp_path / "checkpoints"),
                active_contract_enabled=True,
            )

            model, metrics, pipeline_config = train_lstm(csv_path, config)

            self.assertIsInstance(model, LSTMModel)
            self.assertEqual(model.input_size, 5)
            self.assertEqual(model.output_size, 5)
            self.assertEqual(len(metrics.train_losses), 5)
            self.assertEqual(pipeline_config.parameters, ("pH", "TDS", "turbidity", "temperature", "optical_colour_index"))

    def test_evaluate_on_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            csv_path = tmp_path / "test_data.csv"
            synthetic_series(240).to_csv(csv_path, index=False)

            checkpoint_dir = tmp_path / "checkpoints"
            checkpoint_dir.mkdir()

            config = TrainingConfig(
                random_seed=42,
                num_epochs=3,
                checkpoint_dir=str(checkpoint_dir),
                active_contract_enabled=True,
            )

            model, metrics, _ = train_lstm(csv_path, config)
            checkpoint_path = checkpoint_dir / "lstm_water_quality_5param_v1_best.pt"

            results = evaluate_on_test(checkpoint_path, csv_path)

            self.assertIn("n_test_samples", results)
            self.assertIn("metrics", results)
            self.assertIn("mae", results["metrics"])
            self.assertIn("rmse", results["metrics"])

    def test_inverse_transform_predictions(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15),
        )

        model = LSTMModel()
        model.eval()
        device = torch.device("cpu")

        X_test = result.X_test
        physical_predictions = predict_with_inverse_transform(model, X_test, result, device)

        self.assertEqual(physical_predictions.shape, result.y_test.shape)
        self.assertEqual(physical_predictions.shape[1], 5)


class ModelArchitectureTests(unittest.TestCase):
    def test_architecture_spec(self) -> None:
        model = LSTMModel()
        
        self.assertEqual(model.input_size, 5)
        self.assertEqual(model.hidden_size, 64)
        self.assertEqual(model.num_layers, 2)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 5)

        batch_size = 4
        X = torch.randn(batch_size, 30, 5)
        output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 5))


if __name__ == "__main__":
    unittest.main()




