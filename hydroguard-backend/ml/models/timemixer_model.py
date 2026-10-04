"""TimeMixer model for HydroGuard water quality forecasting.

Based on "TimeMixer: Decomposable Multiscale Mixing for Time Series Forecasting"
https://arxiv.org/abs/2306.09347

TimeMixer uses multi-scale decomposition and mixing to capture both
short-term patterns and long-term trends in time series data.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn


class MultiScaleDecomposition(nn.Module):
    """Multi-scale temporal decomposition module.

    Creates multiple temporal resolutions of the input sequence
    to capture patterns at different time scales.
    """

    def __init__(self, num_scales: int = 3, max_kernel_size: int = 5):
        super().__init__()
        self.num_scales = num_scales
        self.max_kernel_size = max_kernel_size

        # Create pooling layers for different scales
        self.pool_layers = nn.ModuleList()
        for i in range(num_scales):
            kernel_size = max_kernel_size - i * 2
            if kernel_size < 1:
                kernel_size = 1
            pool = nn.AvgPool1d(kernel_size=kernel_size, stride=1, padding=kernel_size // 2)
            self.pool_layers.append(pool)

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        """Decompose input into multiple temporal scales.

        Args:
            x: (batch, seq_len, features)

        Returns:
            List of tensors at different temporal scales
        """
        # Transpose for pooling: (batch, features, seq_len)
        x = x.transpose(1, 2)
        
        scales = []
        for pool in self.pool_layers:
            scaled = pool(x)  # (batch, features, seq_len)
            # Transpose back: (batch, seq_len, features)
            scaled = scaled.transpose(1, 2)
            scales.append(scaled)
        
        return scales


class ScaleMixing(nn.Module):
    """Mixing layer to combine information across temporal scales."""

    def __init__(self, hidden_size: int, num_scales: int, dropout: float = 0.1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_scales = num_scales

        # Linear projections for each scale
        self.scale_projections = nn.ModuleList([
            nn.Linear(hidden_size, hidden_size) for _ in range(num_scales)
        ])

        # Cross-scale attention
        self.cross_scale_attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=4,
            dropout=dropout,
            batch_first=True,
        )

        # Mixing layer
        self.mixing = nn.Sequential(
            nn.Linear(hidden_size * num_scales, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, hidden_size),
        )

    def forward(self, scale_features: list[torch.Tensor]) -> torch.Tensor:
        """Mix features across temporal scales.

        Args:
            scale_features: List of (batch, seq_len, hidden_size) for each scale

        Returns:
            Mixed features: (batch, seq_len, hidden_size)
        """
        batch_size = scale_features[0].size(0)
        seq_len = scale_features[0].size(1)

        # Project each scale
        projected = []
        for i, (features, proj) in enumerate(zip(scale_features, self.scale_projections)):
            proj_features = proj(features)  # (batch, seq_len, hidden_size)
            projected.append(proj_features)

        # Stack scales for attention: (batch, num_scales * seq_len, hidden_size)
        stacked = torch.cat(projected, dim=1)

        # Apply self-attention across all scales
        attended, _ = self.cross_scale_attention(stacked, stacked, stacked)

        # Split back into scales and concatenate along feature dimension
        scale_size = seq_len
        split_features = torch.chunk(attended, self.num_scales, dim=1)
        concatenated = torch.cat(split_features, dim=2)  # (batch, seq_len, hidden_size * num_scales)

        # Apply mixing layer
        mixed = self.mixing(concatenated)  # (batch, seq_len, hidden_size)

        return mixed


class TemporalMixing(nn.Module):
    """Temporal mixing to capture time dependencies within each scale."""

    def __init__(self, hidden_size: int, dropout: float = 0.1):
        super().__init__()
        self.temporal_conv = nn.Conv1d(
            in_channels=hidden_size,
            out_channels=hidden_size,
            kernel_size=3,
            padding=1,
        )
        self.norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.activation = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply temporal mixing.

        Args:
            x: (batch, seq_len, hidden_size)

        Returns:
            Mixed features: (batch, seq_len, hidden_size)
        """
        residual = x

        # Transpose for conv: (batch, hidden_size, seq_len)
        x = x.transpose(1, 2)
        x = self.temporal_conv(x)
        # Transpose back: (batch, seq_len, hidden_size)
        x = x.transpose(1, 2)

        x = self.norm(x)
        x = self.activation(x)
        x = self.dropout(x)

        # Residual connection
        x = x + residual

        return x


class TimeMixer(nn.Module):
    """TimeMixer model for next-day water quality parameter forecasting.

    Architecture:
        Input: (batch, 30, 4) - 30 daily observations of four modelled parameters
        Multi-scale Decomposition: Create multiple temporal resolutions
        Scale Mixing: Combine information across scales
        Temporal Mixing: Capture time dependencies
        Prediction Head: Linear projection to output
        Output: (batch, 4) - next day's four modelled parameters

    Product model inputs: [pH, TDS, turbidity, temperature]. Optical colour has no validated checkpoint.
    """

    def __init__(
        self,
        input_size: int = 4,
        context_length: int = 30,
        hidden_size: int = 64,
        num_scales: int = 3,
        num_mixing_layers: int = 2,
        dropout: float = 0.1,
        output_size: int = 4,
    ):
        super().__init__()
        self.input_size = input_size
        self.context_length = context_length
        self.hidden_size = hidden_size
        self.num_scales = num_scales
        self.num_mixing_layers = num_mixing_layers
        self.dropout = dropout
        self.output_size = output_size

        # Input projection
        self.input_projection = nn.Linear(input_size, hidden_size)

        # Multi-scale decomposition
        self.decomposition = MultiScaleDecomposition(num_scales=num_scales)

        # Scale mixing layers
        self.scale_mixing = ScaleMixing(
            hidden_size=hidden_size,
            num_scales=num_scales,
            dropout=dropout,
        )

        # Temporal mixing layers
        self.temporal_mixing_layers = nn.ModuleList([
            TemporalMixing(hidden_size=hidden_size, dropout=dropout)
            for _ in range(num_mixing_layers)
        ])

        # Prediction head
        self.prediction_head = nn.Sequential(
            nn.Linear(hidden_size * context_length, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, output_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.size(0)

        # Input projection: (batch, seq_len, hidden_size)
        x = self.input_projection(x)

        # Multi-scale decomposition
        scale_features = self.decomposition(x)  # List of (batch, seq_len, hidden_size)

        # Scale mixing
        mixed = self.scale_mixing(scale_features)  # (batch, seq_len, hidden_size)

        # Temporal mixing layers
        for temporal_layer in self.temporal_mixing_layers:
            mixed = temporal_layer(mixed)  # (batch, seq_len, hidden_size)

        # Global pooling across time dimension
        # Alternative: flatten and use all temporal information
        flattened = mixed.reshape(batch_size, -1)  # (batch, seq_len * hidden_size)

        # Prediction
        output = self.prediction_head(flattened)  # (batch, output_size)

        return output

    def get_num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
