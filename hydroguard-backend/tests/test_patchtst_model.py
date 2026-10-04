"""Unit tests for PatchTST water quality forecasting model.

Tests use synthetic data and random tensors for shape verification.
No accuracy claims are made - this is architecture verification only.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.models.patchtst_model import PatchTST


class PatchTSTModelTests(unittest.TestCase):
    def test_model_initialization_default(self) -> None:
        model = PatchTST()
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.context_length, 30)
        self.assertEqual(model.patch_length, 5)
        self.assertEqual(model.stride, 5)
        self.assertEqual(model.d_model, 64)
        self.assertEqual(model.num_heads, 4)
        self.assertEqual(model.num_layers, 2)
        self.assertEqual(model.dropout, 0.1)
        self.assertEqual(model.output_size, 4)

    def test_model_initialization_custom(self) -> None:
        model = PatchTST(
            input_size=4,
            context_length=20,
            patch_length=4,
            stride=4,
            d_model=32,
            num_heads=2,
            num_layers=1,
            dropout=0.2,
            output_size=4,
        )
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.context_length, 20)
        self.assertEqual(model.patch_length, 4)
        self.assertEqual(model.stride, 4)
        self.assertEqual(model.d_model, 32)
        self.assertEqual(model.num_heads, 2)
        self.assertEqual(model.num_layers, 1)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 4)

    def test_num_patches_calculation(self) -> None:
        model = PatchTST(context_length=30, patch_length=5, stride=5)
        expected_patches = (30 - 5) // 5 + 1  # Should be 6
        self.assertEqual(model.num_patches, expected_patches)

    def test_patch_creation_shape(self) -> None:
        model = PatchTST()
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        patches = model._create_patches(X)
        
        # Expected: (batch, num_patches, patch_length * input_size)
        expected_shape = (batch_size, model.num_patches, model.patch_length * model.input_size)
        self.assertEqual(patches.shape, expected_shape)

    def test_forward_pass_shape(self) -> None:
        model = PatchTST()
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 4))

    def test_forward_pass_four_param(self) -> None:
        model = PatchTST(input_size=4, output_size=4)
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 4))

    def test_model_parameter_count(self) -> None:
        model = PatchTST()
        n_params = model.get_num_parameters()
        self.assertGreater(n_params, 0)
        self.assertLess(n_params, 1000000)

    def test_positional_encoding_shape(self) -> None:
        from ml.models.patchtst_model import PositionalEncoding
        
        d_model = 64
        max_len = 100
        pos_enc = PositionalEncoding(d_model, dropout=0.1, max_len=max_len)
        
        batch_size = 8
        seq_len = 10
        x = torch.randn(batch_size, seq_len, d_model)
        output = pos_enc(x)
        
        self.assertEqual(output.shape, (batch_size, seq_len, d_model))


class DeviceTests(unittest.TestCase):
    def test_cpu_device(self) -> None:
        model = PatchTST()
        model = model.to("cpu")
        self.assertEqual(model.patch_embedding.weight.device.type, "cpu")

    def test_auto_device_resolution(self) -> None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = PatchTST()
        model = model.to(device)
        self.assertEqual(model.patch_embedding.weight.device.type, device)


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_save_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "test_checkpoint.pt"
            model = PatchTST()
            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

            # Manually create a checkpoint structure similar to training module
            checkpoint = {
                "epoch": 5,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_loss": 0.123,
                "config": {
                    "input_size": 4,
                    "context_length": 30,
                    "patch_length": 5,
                    "stride": 5,
                    "d_model": 64,
                    "num_heads": 4,
                    "num_layers": 2,
                    "dropout": 0.1,
                    "output_size": 4,
                },
            }
            torch.save(checkpoint, checkpoint_path)

            self.assertTrue(checkpoint_path.exists())

            # Load checkpoint
            loaded_checkpoint = torch.load(checkpoint_path, map_location="cpu")
            new_model = PatchTST()
            new_model.load_state_dict(loaded_checkpoint["model_state_dict"])
            new_optimizer = torch.optim.Adam(new_model.parameters(), lr=0.001)
            new_optimizer.load_state_dict(loaded_checkpoint["optimizer_state_dict"])

            self.assertEqual(loaded_checkpoint["epoch"], 5)
            self.assertAlmostEqual(loaded_checkpoint["val_loss"], 0.123, places=6)

            for p1, p2 in zip(model.parameters(), new_model.parameters()):
                self.assertTrue(torch.allclose(p1, p2))


class ArchitectureTests(unittest.TestCase):
    def test_architecture_components(self) -> None:
        model = PatchTST()
        
        # Check that model has expected components
        self.assertIsInstance(model.patch_embedding, torch.nn.Linear)
        self.assertIsInstance(model.positional_encoding, torch.nn.Module)
        self.assertIsInstance(model.transformer_encoder, torch.nn.TransformerEncoder)
        self.assertIsInstance(model.prediction_head, torch.nn.Sequential)

    def test_patch_embedding_dimensions(self) -> None:
        model = PatchTST()
        # Input to patch embedding: (batch, num_patches, patch_length * input_size)
        # Output: (batch, num_patches, d_model)
        input_dim = model.patch_length * model.input_size
        output_dim = model.d_model
        
        self.assertEqual(model.patch_embedding.in_features, input_dim)
        self.assertEqual(model.patch_embedding.out_features, output_dim)

    def test_prediction_head_dimensions(self) -> None:
        model = PatchTST()
        # Input to prediction head: (batch, num_patches * d_model)
        # Output: (batch, output_size)
        input_dim = model.num_patches * model.d_model
        output_dim = model.output_size
        
        first_layer = model.prediction_head[0]
        last_layer = model.prediction_head[-1]
        
        self.assertEqual(first_layer.in_features, input_dim)
        self.assertEqual(last_layer.out_features, output_dim)


class PatchTSTIntegrationTests(unittest.TestCase):
    def test_end_to_end_forward_pass(self) -> None:
        model = PatchTST()
        model.eval()
        
        batch_size = 4
        X = torch.randn(batch_size, 30, 4)
        
        with torch.no_grad():
            output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 4))
        self.assertFalse(torch.isnan(output).any())
        self.assertFalse(torch.isinf(output).any())

    def test_different_batch_sizes(self) -> None:
        model = PatchTST()
        
        for batch_size in [1, 8, 16, 32]:
            X = torch.randn(batch_size, 30, 4)
            output = model(X)
            self.assertEqual(output.shape, (batch_size, 4))

    def test_gradient_flow(self) -> None:
        model = PatchTST()
        model.train()
        
        X = torch.randn(4, 30, 4)
        y = torch.randn(4, 4)
        
        output = model(X)
        loss = torch.nn.functional.mse_loss(output, y)
        loss.backward()
        
        # Check that gradients are computed
        for param in model.parameters():
            if param.requires_grad:
                self.assertIsNotNone(param.grad)


class FourParameterModeTests(unittest.TestCase):
    def test_four_parameter_model(self) -> None:
        model = PatchTST(input_size=4, output_size=4, context_length=30)
        
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 4))
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.output_size, 4)

    def test_four_parameter_patch_creation(self) -> None:
        model = PatchTST(input_size=4, output_size=4)
        
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        patches = model._create_patches(X)
        
        expected_patch_dim = model.patch_length * model.input_size
        self.assertEqual(patches.shape[2], expected_patch_dim)


class NaNValidationTests(unittest.TestCase):
    def test_nan_detection_logic(self) -> None:
        # Test the NaN detection logic that would be used in training
        X_train_with_nan = np.random.randn(10, 30, 4)
        X_train_with_nan[0, 0, 3] = np.nan
        y_train_with_nan = np.random.randn(10, 4)
        
        has_nan = np.isnan(X_train_with_nan).any() or np.isnan(y_train_with_nan).any()
        self.assertTrue(has_nan)

    def test_clean_data_detection(self) -> None:
        X_train_clean = np.random.randn(10, 30, 4)
        y_train_clean = np.random.randn(10, 4)
        
        has_nan = np.isnan(X_train_clean).any() or np.isnan(y_train_clean).any()
        self.assertFalse(has_nan)


if __name__ == "__main__":
    unittest.main()
