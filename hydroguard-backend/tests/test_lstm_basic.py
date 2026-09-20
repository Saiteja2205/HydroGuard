"""Basic LSTM model tests without pandas dependency."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.models.lstm_model import LSTMModel
from ml.training.train_lstm import (
    TrainingConfig,
    create_data_loaders,
    get_device,
    load_checkpoint,
    save_checkpoint,
    set_random_seed,
)


class LSTMModelBasicTests(unittest.TestCase):
    def test_model_initialization_default(self) -> None:
        model = LSTMModel()
        self.assertEqual(model.input_size, 6)
        self.assertEqual(model.hidden_size, 64)
        self.assertEqual(model.num_layers, 2)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 6)

    def test_model_initialization_custom(self) -> None:
        model = LSTMModel(input_size=4, hidden_size=32, num_layers=1, dropout=0.1, output_size=4)
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.hidden_size, 32)
        self.assertEqual(model.num_layers, 1)
        self.assertEqual(model.dropout, 0.1)
        self.assertEqual(model.output_size, 4)

    def test_forward_pass_shape(self) -> None:
        model = LSTMModel()
        batch_size = 8
        X = torch.randn(batch_size, 30, 6)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 6))

    def test_forward_pass_four_param(self) -> None:
        model = LSTMModel(input_size=4, output_size=4)
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 4))

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


class DataLoaderBasicTests(unittest.TestCase):
    def test_data_loader_creation(self) -> None:
        X_train = np.random.randn(100, 30, 6).astype(np.float32)
        y_train = np.random.randn(100, 6).astype(np.float32)
        X_val = np.random.randn(20, 30, 6).astype(np.float32)
        y_val = np.random.randn(20, 6).astype(np.float32)

        train_loader, val_loader = create_data_loaders(X_train, y_train, X_val, y_val, batch_size=8)

        self.assertEqual(len(train_loader), 13)
        self.assertEqual(len(val_loader), 3)

    def test_data_loader_four_param(self) -> None:
        X_train = np.random.randn(100, 30, 4).astype(np.float32)
        y_train = np.random.randn(100, 4).astype(np.float32)
        X_val = np.random.randn(20, 30, 4).astype(np.float32)
        y_val = np.random.randn(20, 4).astype(np.float32)

        train_loader, val_loader = create_data_loaders(X_train, y_train, X_val, y_val, batch_size=8)

        self.assertEqual(len(train_loader), 13)
        self.assertEqual(len(val_loader), 3)


class CheckpointBasicTests(unittest.TestCase):
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


class ModelArchitectureTests(unittest.TestCase):
    def test_architecture_spec(self) -> None:
        model = LSTMModel()
        
        self.assertEqual(model.input_size, 6)
        self.assertEqual(model.hidden_size, 64)
        self.assertEqual(model.num_layers, 2)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 6)

        batch_size = 4
        X = torch.randn(batch_size, 30, 6)
        output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 6))


if __name__ == "__main__":
    unittest.main()
