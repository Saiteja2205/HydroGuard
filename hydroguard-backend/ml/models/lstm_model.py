"""LSTM model for HydroGuard water quality forecasting."""

from __future__ import annotations

import torch
import torch.nn as nn


class LSTMModel(nn.Module):
    """LSTM model for next-day water quality parameter forecasting.

    Architecture:
        Input: (batch, 30, 6) - 30 days of 6 parameters
        LSTM: 2 layers, hidden_size=64, dropout=0.2
        Output: (batch, 6) - next day's 6 parameters

    Parameters: [pH, TDS, turbidity, temperature, EC, DO]
    """

    def __init__(
        self,
        input_size: int = 6,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        output_size: int = 6,
    ):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.output_size = output_size

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
        )

        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.size(0)
        
        lstm_out, (h_n, c_n) = self.lstm(x)
        
        final_hidden = h_n[-1]
        
        output = self.fc(final_hidden)
        
        return output

    def get_num_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
