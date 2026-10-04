"""PatchTST model for HydroGuard water quality forecasting.

Based on "A Time Series is Worth 64 Words: Long-term Forecasting with Transformers"
https://arxiv.org/abs/2211.14730
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn


class PatchTST(nn.Module):
    """PatchTST model for next-day water quality parameter forecasting.

    Architecture:
        Input: (batch, 30, 4) - 30 daily observations of four modelled parameters
        Patching: Divide sequence into patches of length patch_length
        Embedding: Linear projection to d_model dimensions
        Transformer Encoder: Multi-head self-attention
        Prediction Head: Linear projection to output_size
        Output: (batch, 4) - next day's four modelled parameters

    Product model inputs: [pH, TDS, turbidity, temperature]. Optical colour has no validated checkpoint.
    """

    def __init__(
        self,
        input_size: int = 4,
        context_length: int = 30,
        patch_length: int = 5,
        stride: int = 5,
        d_model: int = 64,
        num_heads: int = 4,
        num_layers: int = 2,
        dropout: float = 0.1,
        output_size: int = 4,
    ):
        super().__init__()
        self.input_size = input_size
        self.context_length = context_length
        self.patch_length = patch_length
        self.stride = stride
        self.d_model = d_model
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.dropout = dropout
        self.output_size = output_size

        # Calculate number of patches
        self.num_patches = (context_length - patch_length) // stride + 1

        # Patch embedding: project each patch to d_model dimensions
        self.patch_embedding = nn.Linear(patch_length * input_size, d_model)

        # Positional encoding
        self.positional_encoding = PositionalEncoding(d_model, dropout, max_len=self.num_patches)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Prediction head
        self.prediction_head = nn.Sequential(
            nn.Linear(d_model * self.num_patches, d_model),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, output_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.size(0)
        
        # Create patches: (batch, num_patches, patch_length * input_size)
        patches = self._create_patches(x)
        
        # Patch embedding: (batch, num_patches, d_model)
        patch_embeddings = self.patch_embedding(patches)
        
        # Add positional encoding
        patch_embeddings = self.positional_encoding(patch_embeddings)
        
        # Transformer encoding: (batch, num_patches, d_model)
        encoded = self.transformer_encoder(patch_embeddings)
        
        # Flatten for prediction head: (batch, num_patches * d_model)
        flattened = encoded.reshape(batch_size, -1)
        
        # Prediction: (batch, output_size)
        output = self.prediction_head(flattened)
        
        return output

    def _create_patches(self, x: torch.Tensor) -> torch.Tensor:
        """Convert input sequence into patches.

        Args:
            x: (batch, context_length, input_size)

        Returns:
            patches: (batch, num_patches, patch_length * input_size)
        """
        batch_size, seq_len, features = x.shape
        
        # Use unfold to create patches
        # unfold(dimension, size, step)
        patches = x.unfold(dimension=1, size=self.patch_length, step=self.stride)
        
        # patches shape: (batch, num_patches, input_size, patch_length)
        # Reshape to: (batch, num_patches, patch_length * input_size)
        patches = patches.contiguous().view(batch_size, self.num_patches, -1)
        
        return patches

    def get_num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer."""

    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Add positional encoding to input.

        Args:
            x: (batch, seq_len, d_model)

        Returns:
            x with positional encoding added
        """
        x = x + self.pe[:x.size(1), :]
        return self.dropout(x)
