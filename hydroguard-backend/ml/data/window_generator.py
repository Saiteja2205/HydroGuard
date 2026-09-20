"""Sliding windows for next-day forecasting without future leakage."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from ml.data.validator import PARAMETERS

WINDOW_SIZE = 30


def create_sliding_windows(
    values: np.ndarray,
    window_size: int = WINDOW_SIZE,
    mode: Literal["multivariate", "univariate"] = "multivariate",
    parameter_index: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) where X is the previous ``window_size`` days.

    Multivariate:
        X shape (n_samples, window_size, n_features)
        y shape (n_samples, n_features)

    Univariate (one parameter):
        X shape (n_samples, window_size, 1)
        y shape (n_samples, 1)

    Sample i uses rows ``[i, i+window_size)`` to predict row ``i+window_size``.
    The target day is never included in X.
    """
    if window_size < 1:
        raise ValueError("window_size must be >= 1")
    array = np.asarray(values, dtype=float)
    if array.ndim != 2:
        raise ValueError(f"Expected 2D array (time, features), got shape {array.shape}")

    if mode == "univariate":
        if parameter_index is None:
            raise ValueError("univariate mode requires parameter_index")
        array = array[:, parameter_index : parameter_index + 1]
    elif mode != "multivariate":
        raise ValueError("mode must be 'multivariate' or 'univariate'")

    n_time, n_features = array.shape
    n_samples = n_time - window_size
    if n_samples <= 0:
        return (
            np.empty((0, window_size, n_features), dtype=float),
            np.empty((0, n_features), dtype=float),
        )

    X = np.empty((n_samples, window_size, n_features), dtype=float)
    y = np.empty((n_samples, n_features), dtype=float)
    for i in range(n_samples):
        X[i] = array[i : i + window_size]
        y[i] = array[i + window_size]
    return X, y


def create_univariate_windows(
    values: np.ndarray,
    window_size: int = WINDOW_SIZE,
    columns: tuple[str, ...] = PARAMETERS,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-parameter windows for later univariate model experiments."""
    return {
        column: create_sliding_windows(
            values,
            window_size=window_size,
            mode="univariate",
            parameter_index=index,
        )
        for index, column in enumerate(columns)
    }


def assert_no_future_leakage(
    values: np.ndarray,
    X: np.ndarray,
    y: np.ndarray,
    window_size: int,
) -> None:
    """Raise if any window includes the target row or a later row."""
    for i in range(len(y)):
        expected_x = values[i : i + window_size]
        expected_y = values[i + window_size]
        if not np.allclose(X[i], expected_x, equal_nan=True):
            raise AssertionError(f"Window {i} does not match source rows [{i}:{i + window_size}).")
        if not np.allclose(y[i], expected_y, equal_nan=True):
            raise AssertionError(f"Target {i} is not source row {i + window_size}.")
        # Target index is i+window_size; last X index is i+window_size-1.
        if i + window_size - 1 >= i + window_size:
            raise AssertionError("X includes the target timestep.")


def target_dates_for_windows(
    index: pd.DatetimeIndex,
    window_size: int,
) -> pd.DatetimeIndex:
    if len(index) <= window_size:
        return pd.DatetimeIndex([], tz=index.tz, name=index.name)
    return index[window_size:]
