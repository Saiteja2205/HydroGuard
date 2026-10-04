"""Unit tests for TimeMixer water quality forecasting model.

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

from ml.models.timemixer_model import TimeMixer


class TimeMixerModelTests(unittest.TestCase):
    def test_model_initialization_default(self) -> None:
        model = TimeMixer()
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.context_length, 30)
        self.assertEqual(model.hidden_size, 64)
        self.assertEqual(model.num_scales, 3)
        self.assertEqual(model.num_mixing_layers, 2)
        self.assertEqual(model.dropout, 0.1)
        self.assertEqual(model.output_size, 4)

    def test_model_initialization_custom(self) -> None:
        model = TimeMixer(
            input_size=4,
            context_length=20,
            hidden_size=32,
            num_scales=2,
            num_mixing_layers=1,
            dropout=0.2,
            output_size=4,
        )
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.context_length, 20)
        self.assertEqual(model.hidden_size, 32)
        self.assertEqual(model.num_scales, 2)
        self.assertEqual(model.num_mixing_layers, 1)
        self.assertEqual(model.dropout, 0.2)
        self.assertEqual(model.output_size, 4)

    def test_forward_pass_shape(self) -> None:
        model = TimeMixer()
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 4))

    def test_forward_pass_four_param(self) -> None:
        model = TimeMixer(input_size=4, output_size=4)
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        self.assertEqual(output.shape, (batch_size, 4))

    def test_model_parameter_count(self) -> None:
        model = TimeMixer()
        n_params = model.get_num_parameters()
        self.assertGreater(n_params, 0)
        self.assertLess(n_params, 1000000)

    def test_input_projection(self) -> None:
        model = TimeMixer()
        # Input projection should map input_size to hidden_size
        self.assertEqual(model.input_projection.in_features, model.input_size)
        self.assertEqual(model.input_projection.out_features, model.hidden_size)


class MultiScaleDecompositionTests(unittest.TestCase):
    def test_decomposition_initialization(self) -> None:
        from ml.models.timemixer_model import MultiScaleDecomposition
        
        decomp = MultiScaleDecomposition(num_scales=3, max_kernel_size=5)
        self.assertEqual(decomp.num_scales, 3)
        self.assertEqual(len(decomp.pool_layers), 3)

    def test_decomposition_output_shapes(self) -> None:
        from ml.models.timemixer_model import MultiScaleDecomposition
        
        decomp = MultiScaleDecomposition(num_scales=3, max_kernel_size=5)
        batch_size = 8
        seq_len = 30
        features = 6
        X = torch.randn(batch_size, seq_len, features)
        
        scales = decomp(X)
        
        self.assertEqual(len(scales), 3)
        for scale in scales:
            self.assertEqual(scale.shape[0], batch_size)
            self.assertEqual(scale.shape[2], features)

    def test_decomposition_different_scales(self) -> None:
        from ml.models.timemixer_model import MultiScaleDecomposition
        
        decomp = MultiScaleDecomposition(num_scales=2, max_kernel_size=3)
        X = torch.randn(4, 20, 4)
        
        scales = decomp(X)
        
        self.assertEqual(len(scales), 2)
        # Each scale should have the same sequence length due to padding
        self.assertEqual(scales[0].shape[1], scales[1].shape[1])


class ScaleMixingTests(unittest.TestCase):
    def test_scale_mixing_initialization(self) -> None:
        from ml.models.timemixer_model import ScaleMixing
        
        mixing = ScaleMixing(hidden_size=64, num_scales=3, dropout=0.1)
        self.assertEqual(mixing.hidden_size, 64)
        self.assertEqual(mixing.num_scales, 3)
        self.assertEqual(len(mixing.scale_projections), 3)

    def test_scale_mixing_output_shape(self) -> None:
        from ml.models.timemixer_model import ScaleMixing
        
        mixing = ScaleMixing(hidden_size=64, num_scales=3, dropout=0.1)
        batch_size = 8
        seq_len = 30
        
        # Create dummy scale features
        scale_features = [torch.randn(batch_size, seq_len, 64) for _ in range(3)]
        
        mixed = mixing(scale_features)
        
        self.assertEqual(mixed.shape, (batch_size, seq_len, 64))


class TemporalMixingTests(unittest.TestCase):
    def test_temporal_mixing_initialization(self) -> None:
        from ml.models.timemixer_model import TemporalMixing
        
        temporal = TemporalMixing(hidden_size=64, dropout=0.1)
        self.assertEqual(temporal.temporal_conv.in_channels, 64)
        self.assertEqual(temporal.temporal_conv.out_channels, 64)

    def test_temporal_mixing_output_shape(self) -> None:
        from ml.models.timemixer_model import TemporalMixing
        
        temporal = TemporalMixing(hidden_size=64, dropout=0.1)
        batch_size = 8
        seq_len = 30
        X = torch.randn(batch_size, seq_len, 64)
        
        output = temporal(X)
        
        self.assertEqual(output.shape, (batch_size, seq_len, 64))

    def test_temporal_mixing_residual_connection(self) -> None:
        from ml.models.timemixer_model import TemporalMixing
        
        temporal = TemporalMixing(hidden_size=64, dropout=0.0)  # No dropout for deterministic test
        X = torch.randn(4, 20, 64)
        
        output = temporal(X)
        
        # Output should have same shape as input
        self.assertEqual(output.shape, X.shape)


class ArchitectureTests(unittest.TestCase):
    def test_architecture_components(self) -> None:
        model = TimeMixer()
        
        # Check that model has expected components
        self.assertIsInstance(model.input_projection, torch.nn.Linear)
        self.assertIsInstance(model.decomposition, torch.nn.Module)
        self.assertIsInstance(model.scale_mixing, torch.nn.Module)
        self.assertIsInstance(model.temporal_mixing_layers, torch.nn.ModuleList)
        self.assertIsInstance(model.prediction_head, torch.nn.Sequential)

    def test_prediction_head_dimensions(self) -> None:
        model = TimeMixer()
        # Input to prediction head: (batch, context_length * hidden_size)
        # Output: (batch, output_size)
        input_dim = model.context_length * model.hidden_size
        output_dim = model.output_size
        
        first_layer = model.prediction_head[0]
        last_layer = model.prediction_head[-1]
        
        self.assertEqual(first_layer.in_features, input_dim)
        self.assertEqual(last_layer.out_features, output_dim)


class DeviceTests(unittest.TestCase):
    def test_cpu_device(self) -> None:
        model = TimeMixer()
        model = model.to("cpu")
        self.assertEqual(model.input_projection.weight.device.type, "cpu")

    def test_auto_device_resolution(self) -> None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = TimeMixer()
        model = model.to(device)
        self.assertEqual(model.input_projection.weight.device.type, device)


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_save_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = Path(tmpdir) / "test_checkpoint.pt"
            model = TimeMixer()
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
                    "hidden_size": 64,
                    "num_scales": 3,
                    "num_mixing_layers": 2,
                    "dropout": 0.1,
                    "output_size": 4,
                },
            }
            torch.save(checkpoint, checkpoint_path)

            self.assertTrue(checkpoint_path.exists())

            # Load checkpoint
            loaded_checkpoint = torch.load(checkpoint_path, map_location="cpu")
            new_model = TimeMixer()
            new_model.load_state_dict(loaded_checkpoint["model_state_dict"])
            new_optimizer = torch.optim.Adam(new_model.parameters(), lr=0.001)
            new_optimizer.load_state_dict(loaded_checkpoint["optimizer_state_dict"])

            self.assertEqual(loaded_checkpoint["epoch"], 5)
            self.assertAlmostEqual(loaded_checkpoint["val_loss"], 0.123, places=6)

            for p1, p2 in zip(model.parameters(), new_model.parameters()):
                self.assertTrue(torch.allclose(p1, p2))


class TimeMixerIntegrationTests(unittest.TestCase):
    def test_end_to_end_forward_pass(self) -> None:
        model = TimeMixer()
        model.eval()
        
        batch_size = 4
        X = torch.randn(batch_size, 30, 4)
        
        with torch.no_grad():
            output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 4))
        self.assertFalse(torch.isnan(output).any())
        self.assertFalse(torch.isinf(output).any())

    def test_different_batch_sizes(self) -> None:
        model = TimeMixer()
        
        for batch_size in [1, 8, 16, 32]:
            X = torch.randn(batch_size, 30, 4)
            output = model(X)
            self.assertEqual(output.shape, (batch_size, 4))

    def test_gradient_flow(self) -> None:
        model = TimeMixer()
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
        model = TimeMixer(input_size=4, output_size=4, context_length=30)
        
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        output = model(X)
        
        self.assertEqual(output.shape, (batch_size, 4))
        self.assertEqual(model.input_size, 4)
        self.assertEqual(model.output_size, 4)

    def test_four_parameter_decomposition(self) -> None:
        model = TimeMixer(input_size=4, output_size=4)
        
        batch_size = 8
        X = torch.randn(batch_size, 30, 4)
        
        # Project to hidden space
        projected = model.input_projection(X)
        
        # Decompose
        scales = model.decomposition(projected)
        
        self.assertEqual(len(scales), model.num_scales)
        for scale in scales:
            self.assertEqual(scale.shape[0], batch_size)
            self.assertEqual(scale.shape[2], model.hidden_size)


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


class MultiScaleTests(unittest.TestCase):
    def test_different_num_scales(self) -> None:
        for num_scales in [2, 3, 4]:
            model = TimeMixer(num_scales=num_scales)
            self.assertEqual(model.num_scales, num_scales)
            
            # Test forward pass
            X = torch.randn(4, 30, 4)
            output = model(X)
            self.assertEqual(output.shape, (4, 4))

    def test_different_mixing_layers(self) -> None:
        for num_layers in [1, 2, 3]:
            model = TimeMixer(num_mixing_layers=num_layers)
            self.assertEqual(model.num_mixing_layers, num_layers)
            self.assertEqual(len(model.temporal_mixing_layers), num_layers)
            
            # Test forward pass
            X = torch.randn(4, 30, 4)
            output = model(X)
            self.assertEqual(output.shape, (4, 4))


if __name__ == "__main__":
    unittest.main()
