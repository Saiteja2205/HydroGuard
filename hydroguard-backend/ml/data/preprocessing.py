"""Daily resampling, causal missing-value handling, splits, and scaling."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from ml.data.validator import PARAMETERS

AGGREGATIONS = {"mean", "median", "last"}
MISSING_STRATEGIES = {"causal_ffill", "none"}
SCALER_TYPES = {"standard", "minmax"}


@dataclass
class FeatureScaler:
    """Scalers fitted only on training rows of *available* parameters.

    Unavailable parameters (including unvalidated optical colour) are
    not filled with fake measurements. Their inverse-transformed slots stay
    NaN.
    """

    columns: tuple[str, ...]
    available_columns: tuple[str, ...]
    scaler_type: str
    _scaler: StandardScaler | MinMaxScaler | None = None

    @property
    def available_index(self) -> np.ndarray:
        return np.array(
            [self.columns.index(column) for column in self.available_columns],
            dtype=int,
        )

    def fit(self, train_df: pd.DataFrame) -> FeatureScaler:
        if not self.available_columns:
            self._scaler = None
            return self
        if train_df[list(self.available_columns)].isna().any().any():
            raise ValueError(
                "Training data still contains NaN in available columns. "
                "Impute or drop those rows before fitting the scaler."
            )
        if self.scaler_type == "standard":
            self._scaler = StandardScaler()
        elif self.scaler_type == "minmax":
            self._scaler = MinMaxScaler()
        else:
            raise ValueError(f"Unknown scaler_type: {self.scaler_type}")
        self._scaler.fit(train_df[list(self.available_columns)].to_numpy(dtype=float))
        return self

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        values = np.full((len(frame), len(self.columns)), np.nan, dtype=float)
        if not self.available_columns:
            return values
        if self._scaler is None:
            raise RuntimeError("FeatureScaler.transform() called before fit().")
        transformed = self._scaler.transform(
            frame[list(self.available_columns)].to_numpy(dtype=float)
        )
        values[:, self.available_index] = transformed
        return values

    def inverse_transform(self, y_scaled: np.ndarray) -> np.ndarray:
        """Map scaled predictions back to physical units.

        Shape: (n_samples, n_parameters). Unavailable columns stay NaN.
        """
        array = np.asarray(y_scaled, dtype=float)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.shape[-1] != len(self.columns):
            raise ValueError(
                f"Expected last dimension {len(self.columns)}, got {array.shape[-1]}"
            )
        restored = np.full(array.shape, np.nan, dtype=float)
        if not self.available_columns or self._scaler is None:
            return restored
        restored[..., self.available_index] = self._scaler.inverse_transform(
            array[..., self.available_index]
        )
        return restored

    def training_mean(self) -> dict[str, float]:
        if self._scaler is None or not hasattr(self._scaler, "mean_"):
            return {}
        return {
            column: float(value)
            for column, value in zip(self.available_columns, self._scaler.mean_)
        }


def sort_chronologically(frame: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in frame.columns:
        raise ValueError("Cannot sort: timestamp column is missing.")
    return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def collapse_duplicate_timestamps(
    frame: pd.DataFrame,
    parameters: tuple[str, ...] = PARAMETERS,
    how: str = "mean",
) -> pd.DataFrame:
    """Reduce exact duplicate timestamps to one row.

    ``how`` is mean (default), median, first, or last. This is reported by the
    validator; it does not invent new sensor readings.
    """
    if how in {"mean", "median"}:
        grouped = frame.groupby("timestamp", dropna=False, sort=True)
        values = grouped[list(parameters)].agg(how)
        return values.reset_index()
    if how in {"first", "last"}:
        return (
            frame.sort_values("timestamp", kind="mergesort")
            .drop_duplicates(subset=["timestamp"], keep=how)
            .reset_index(drop=True)
        )
    raise ValueError(f"Unknown duplicate strategy: {how}")


def resample_daily(
    frame: pd.DataFrame,
    parameters: tuple[str, ...] = PARAMETERS,
    how: str = "mean",
) -> pd.DataFrame:
    """One calendar day (UTC) per row, regular daily frequency.

    Multiple intra-day measurements become a single representative value.
    Days with no measurements appear as NaN (later handled explicitly).
    """
    if how not in AGGREGATIONS:
        raise ValueError(f"daily_aggregation must be one of {sorted(AGGREGATIONS)}")

    indexed = frame.set_index("timestamp")
    if indexed.index.tz is None:
        indexed = indexed.tz_localize("UTC")
    else:
        indexed = indexed.tz_convert("UTC")

    numeric = indexed[list(parameters)]
    if how == "mean":
        daily = numeric.resample("D").mean()
    elif how == "median":
        daily = numeric.resample("D").median()
    else:
        daily = numeric.resample("D").last()
    daily.index.name = "timestamp"
    return daily


def identify_unavailable_columns(
    daily: pd.DataFrame,
    parameters: tuple[str, ...] = PARAMETERS,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A column is unavailable when it has zero non-NaN daily values.

    An unavailable parameter is never imputed.
    Unavailable columns are not imputed.
    """
    available: list[str] = []
    unavailable: list[str] = []
    for column in parameters:
        if column not in daily.columns or daily[column].notna().sum() == 0:
            unavailable.append(column)
        else:
            available.append(column)
    return tuple(available), tuple(unavailable)


def apply_missing_strategy(
    daily: pd.DataFrame,
    available_columns: tuple[str, ...],
    strategy: str = "causal_ffill",
) -> pd.DataFrame:
    """Fill gaps only on columns that already contain real values.

    Default ``causal_ffill`` (last observation carried forward):
    - uses only past values (no future leakage)
    - does not back-fill
    - does not interpolate (interpolation would use future points)
    - does not touch unavailable columns

    Leading NaNs (before the first valid observation) remain NaN and should
    be dropped by ``drop_incomplete_available_rows``.
    """
    if strategy not in MISSING_STRATEGIES:
        raise ValueError(f"missing_strategy must be one of {sorted(MISSING_STRATEGIES)}")
    filled = daily.copy()
    if strategy == "none" or not available_columns:
        return filled
    filled[list(available_columns)] = filled[list(available_columns)].ffill()
    return filled


def drop_incomplete_available_rows(
    daily: pd.DataFrame,
    available_columns: tuple[str, ...],
) -> pd.DataFrame:
    if not available_columns:
        return daily.copy()
    return daily.dropna(subset=list(available_columns)).copy()


def chronological_split(
    daily: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Contiguous time split. Not random. Ratios must sum to 1."""
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-8:
        raise ValueError(
            f"Split ratios must sum to 1.0, got {train_ratio} + {val_ratio} + {test_ratio} = {total}"
        )
    if any(ratio < 0 for ratio in (train_ratio, val_ratio, test_ratio)):
        raise ValueError("Split ratios must be non-negative.")
    n_rows = len(daily)
    if n_rows < 3:
        raise ValueError(f"Need at least 3 daily rows to split, got {n_rows}.")

    n_train = int(n_rows * train_ratio)
    n_val = int(n_rows * val_ratio)
    n_test = n_rows - n_train - n_val
    if min(n_train, n_val, n_test) < 1:
        raise ValueError(
            f"Split produced an empty set (n={n_rows}, "
            f"train={n_train}, val={n_val}, test={n_test}). "
            "Provide more daily rows or adjust ratios."
        )

    train_df = daily.iloc[:n_train].copy()
    val_df = daily.iloc[n_train : n_train + n_val].copy()
    test_df = daily.iloc[n_train + n_val :].copy()
    _assert_chronological_parts(train_df, val_df, test_df)
    return train_df, val_df, test_df


def _assert_chronological_parts(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> None:
    if train_df.index.max() >= val_df.index.min():
        raise ValueError("Train/validation split leaked: train timestamps overlap validation.")
    if val_df.index.max() >= test_df.index.min():
        raise ValueError("Validation/test split leaked: validation timestamps overlap test.")


def fit_scaler_on_train(
    train_df: pd.DataFrame,
    available_columns: tuple[str, ...],
    columns: tuple[str, ...] = PARAMETERS,
    scaler_type: str = "standard",
) -> FeatureScaler:
    if scaler_type not in SCALER_TYPES:
        raise ValueError(f"scaler_type must be one of {sorted(SCALER_TYPES)}")
    scaler = FeatureScaler(
        columns=columns,
        available_columns=available_columns,
        scaler_type=scaler_type,
    )
    return scaler.fit(train_df)
