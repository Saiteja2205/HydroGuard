"""Training script for PatchTST water quality forecasting model."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from ml.data import run_pipeline, PipelineConfig
from ml.data.validator import PARAMETERS
from ml.models.patchtst_model import PatchTST


@dataclass
class PatchTSTTrainingConfig:
    model_name: str = "patchtst_water_quality_5param_v1"
    input_size: int = 5
    context_length: int = 30
    patch_length: int = 5
    stride: int = 5
    d_model: int = 64
    num_heads: int = 4
    num_layers: int = 2
    dropout: float = 0.1
    output_size: int = 5
    batch_size: int = 32
    learning_rate: float = 0.001
    num_epochs: int = 100
    early_stopping_patience: int = 10
    random_seed: int = 42
    checkpoint_dir: str = "artifacts/checkpoints"
    device: str = "auto"
    active_contract_enabled: bool = True
    parameters: tuple[str, ...] | None = None


@dataclass
class TrainingMetrics:
    train_losses: list[float] = field(default_factory=list)
    val_losses: list[float] = field(default_factory=list)
    best_val_loss: float = float("inf")
    best_epoch: int = 0
    final_epoch: int = 0


def set_random_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def get_device(device_config: str) -> torch.device:
    if device_config == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        else:
            return torch.device("cpu")
    return torch.device(device_config)


def create_data_loaders(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    batch_size: int,
) -> tuple[DataLoader, DataLoader]:
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

    return train_loader, val_loader


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0

    for X_batch, y_batch in train_loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        optimizer.zero_grad()
        outputs = model(X_batch)
        loss = criterion(outputs, y_batch)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / n_batches if n_batches > 0 else 0.0


def validate(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.eval()
    total_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)

            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)

            total_loss += loss.item()
            n_batches += 1

    return total_loss / n_batches if n_batches > 0 else 0.0


def save_checkpoint(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    val_loss: float,
    config: PatchTSTTrainingConfig,
    checkpoint_path: Path,
) -> None:
    checkpoint = {
        "epoch": epoch,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "val_loss": val_loss,
        "feature_count": len(PARAMETERS),
        "parameters": list(PARAMETERS),
        "model_version": "five-param-v1",
        "config": {
            "input_size": config.input_size,
            "context_length": config.context_length,
            "patch_length": config.patch_length,
            "stride": config.stride,
            "d_model": config.d_model,
            "num_heads": config.num_heads,
            "num_layers": config.num_layers,
            "dropout": config.dropout,
            "output_size": config.output_size,
        },
    }
    torch.save(checkpoint, checkpoint_path)


def load_checkpoint(
    checkpoint_path: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
) -> dict[str, Any]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"])
    if optimizer is not None and "optimizer_state_dict" in checkpoint:
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
    return checkpoint


def train_patchtst(
    data_source: str | Path,
    config: PatchTSTTrainingConfig | None = None,
) -> tuple[PatchTST, TrainingMetrics, PipelineConfig]:
    config = config or PatchTSTTrainingConfig()
    set_random_seed(config.random_seed)

    device = get_device(config.device)
    print(f"Using device: {device}")

    if not config.active_contract_enabled or (config.parameters is not None and tuple(config.parameters) != PARAMETERS):
        raise ValueError(f"HydroGuard forecasting is restricted to {PARAMETERS}; legacy/extra parameters are unsupported.")
    pipeline_config = PipelineConfig(parameters=PARAMETERS)
    config.input_size = len(PARAMETERS)
    config.output_size = len(PARAMETERS)

    result = run_pipeline(data_source, pipeline_config)

    X_train = result.X_train
    y_train = result.y_train
    X_val = result.X_val
    y_val = result.y_val
    X_test = result.X_test
    y_test = result.y_test

    if X_train.shape[0] == 0:
        raise ValueError(
            f"Training set is empty. Need at least {pipeline_config.window_size + 1} days. "
            f"Current dataset has {result.diagnostics['n_processed_daily_rows']} daily rows."
        )

    print(f"Training data shape: X={X_train.shape}, y={y_train.shape}")
    print(f"Validation data shape: X={X_val.shape}, y={y_val.shape}")
    print(f"Available columns: {result.diagnostics['available_columns']}")
    print(f"Unavailable columns: {result.diagnostics['unavailable_columns']}")

    train_loader, val_loader = create_data_loaders(
        X_train, y_train, X_val, y_val, config.batch_size
    )

    model = PatchTST(
        input_size=config.input_size,
        context_length=config.context_length,
        patch_length=config.patch_length,
        stride=config.stride,
        d_model=config.d_model,
        num_heads=config.num_heads,
        num_layers=config.num_layers,
        dropout=config.dropout,
        output_size=config.output_size,
    ).to(device)

    print(f"Model parameters: {model.get_num_parameters()}")
    print(f"Number of patches: {model.num_patches}")

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)

    checkpoint_dir = Path(config.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_checkpoint_path = checkpoint_dir / f"{config.model_name}_best.pt"
    last_checkpoint_path = checkpoint_dir / f"{config.model_name}_last.pt"

    metrics = TrainingMetrics()
    patience_counter = 0

    for epoch in range(config.num_epochs):
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss = validate(model, val_loader, criterion, device)

        metrics.train_losses.append(train_loss)
        metrics.val_losses.append(val_loss)

        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(
                f"Epoch {epoch + 1}/{config.num_epochs} - "
                f"Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}"
            )

        if val_loss < metrics.best_val_loss:
            metrics.best_val_loss = val_loss
            metrics.best_epoch = epoch + 1
            save_checkpoint(model, optimizer, epoch + 1, val_loss, config, best_checkpoint_path)
            patience_counter = 0
        else:
            patience_counter += 1

        if patience_counter >= config.early_stopping_patience:
            print(f"Early stopping at epoch {epoch + 1}")
            break

    metrics.final_epoch = epoch + 1
    save_checkpoint(model, optimizer, metrics.final_epoch, metrics.val_losses[-1], config, last_checkpoint_path)

    print(f"\nTraining completed. Best val loss: {metrics.best_val_loss:.6f} at epoch {metrics.best_epoch}")
    print(f"Best checkpoint saved to: {best_checkpoint_path}")

    return model, metrics, pipeline_config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PatchTST water quality forecasting model")
    parser.add_argument(
        "--data-source",
        type=str,
        default="data/demo_water_quality.csv",
        help="Path to training data CSV file"
    )
    parser.add_argument(
        "--parameters",
        type=str,
        nargs="+",
        default=None,
        help="List of parameters to use (e.g., --parameters pH TDS turbidity temperature)"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for training"
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.001,
        help="Learning rate"
    )
    parser.add_argument(
        "--patch-length",
        type=int,
        default=5,
        help="Patch length"
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=5,
        help="Stride for patch creation"
    )
    parser.add_argument(
        "--d-model",
        type=int,
        default=64,
        help="Transformer model dimension"
    )
    parser.add_argument(
        "--num-heads",
        type=int,
        default=4,
        help="Number of attention heads"
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of transformer layers"
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        help="Dropout rate"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed"
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="artifacts/checkpoints",
        help="Directory to save checkpoints"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device to use (auto, cpu, cuda)"
    )
    
    args = parser.parse_args()
    
    if args.parameters is not None and tuple(args.parameters) != PARAMETERS:
        parser.error(f"HydroGuard forecasting only supports: {', '.join(PARAMETERS)}")
    
    config = PatchTSTTrainingConfig(
        random_seed=args.seed,
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        patch_length=args.patch_length,
        stride=args.stride,
        d_model=args.d_model,
        num_heads=args.num_heads,
        num_layers=args.num_layers,
        dropout=args.dropout,
        checkpoint_dir=args.checkpoint_dir,
        device=args.device,
        active_contract_enabled=True,
        parameters=PARAMETERS,
    )

    model, metrics, pipeline_config = train_patchtst(
        data_source=args.data_source,
        config=config,
    )
