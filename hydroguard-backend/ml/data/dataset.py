"""End-to-end shared dataset pipeline for HydroGuard forecasting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from ml.data.loader import load_csv
from ml.data.preprocessing import (
    FeatureScaler,
    apply_missing_strategy,
    chronological_split,
    collapse_duplicate_timestamps,
    drop_incomplete_available_rows,
    fit_scaler_on_train,
    identify_unavailable_columns,
    resample_daily,
    sort_chronologically,
)
from ml.data.validator import PARAMETERS, ValidationReport, validate_raw_frame
from ml.data.window_generator import (
    WINDOW_SIZE,
    assert_no_future_leakage,
    create_sliding_windows,
    create_univariate_windows,
    target_dates_for_windows,
)

Mode = Literal["multivariate", "univariate"]


@dataclass
class PipelineConfig:
    window_size: int = WINDOW_SIZE
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    daily_aggregation: str = "mean"
    duplicate_strategy: str = "mean"
    missing_strategy: str = "causal_ffill"
    scaler_type: str = "standard"
    mode: Mode = "multivariate"
    parameters: tuple[str, ...] = PARAMETERS
    drop_leading_incomplete_days: bool = True


@dataclass
class PipelineResult:
    processed_df: pd.DataFrame
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    scalers: FeatureScaler
    X_train: np.ndarray | dict[str, np.ndarray]
    y_train: np.ndarray | dict[str, np.ndarray]
    X_val: np.ndarray | dict[str, np.ndarray]
    y_val: np.ndarray | dict[str, np.ndarray]
    X_test: np.ndarray | dict[str, np.ndarray]
    y_test: np.ndarray | dict[str, np.ndarray]
    unavailable_columns: tuple[str, ...]
    column_availability: dict[str, bool]
    diagnostics: dict[str, Any] = field(default_factory=dict)
    config: PipelineConfig = field(default_factory=PipelineConfig)
    validation_report: ValidationReport | None = None
    univariate_windows: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] | None = None

    def inverse_transform_predictions(self, y_scaled: np.ndarray) -> np.ndarray:
        """Invert scaling for multivariate predictions of shape (n, 6)."""
        return self.scalers.inverse_transform(y_scaled)


def run_pipeline(
    source: str | Path | pd.DataFrame,
    config: PipelineConfig | None = None,
) -> PipelineResult:
    """Load → validate → daily series → split → scale(train only) → windows.

    ``processed_df`` / split frames are in physical units.
    ``X_*`` / ``y_*`` are scaled. Unavailable parameters remain NaN.
    """
    config = config or PipelineConfig()
    raw = source if isinstance(source, pd.DataFrame) else load_csv(source)
    validated, report = validate_raw_frame(raw)
    validated = validated.dropna(subset=["timestamp"]).copy()

    sorted_frame = sort_chronologically(validated)
    collapsed = collapse_duplicate_timestamps(
        sorted_frame,
        parameters=config.parameters,
        how=config.duplicate_strategy,
    )
    daily = resample_daily(
        collapsed,
        parameters=config.parameters,
        how=config.daily_aggregation,
    )
    available, unavailable = identify_unavailable_columns(daily, config.parameters)
    filled = apply_missing_strategy(daily, available, strategy=config.missing_strategy)
    if config.drop_leading_incomplete_days:
        processed = drop_incomplete_available_rows(filled, available)
    else:
        processed = filled

    if processed.empty:
        raise ValueError("No daily rows remain after resampling and missing-value handling.")

    train_df, val_df, test_df = chronological_split(
        processed,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
    )
    scaler = fit_scaler_on_train(
        train_df,
        available_columns=available,
        columns=config.parameters,
        scaler_type=config.scaler_type,
    )

    train_scaled = scaler.transform(train_df)
    val_scaled = scaler.transform(val_df)
    test_scaled = scaler.transform(test_df)

    X_train, y_train = create_sliding_windows(train_scaled, config.window_size, mode="multivariate")
    X_val, y_val = create_sliding_windows(val_scaled, config.window_size, mode="multivariate")
    X_test, y_test = create_sliding_windows(test_scaled, config.window_size, mode="multivariate")

    for name, source_values, X, y in (
        ("train", train_scaled, X_train, y_train),
        ("val", val_scaled, X_val, y_val),
        ("test", test_scaled, X_test, y_test),
    ):
        if len(y) > 0:
            assert_no_future_leakage(source_values, X, y, config.window_size)

    univariate = None
    if config.mode == "univariate":
        univariate = {
            "train": create_univariate_windows(train_scaled, config.window_size, config.parameters),
            "val": create_univariate_windows(val_scaled, config.window_size, config.parameters),
            "test": create_univariate_windows(test_scaled, config.window_size, config.parameters),
        }
        X_train = {name: arrays[0] for name, arrays in univariate["train"].items()}
        y_train = {name: arrays[1] for name, arrays in univariate["train"].items()}
        X_val = {name: arrays[0] for name, arrays in univariate["val"].items()}
        y_val = {name: arrays[1] for name, arrays in univariate["val"].items()}
        X_test = {name: arrays[0] for name, arrays in univariate["test"].items()}
        y_test = {name: arrays[1] for name, arrays in univariate["test"].items()}

    diagnostics = {
        "n_raw_rows": report.n_rows,
        "n_duplicate_timestamp_rows": report.n_duplicate_timestamps,
        "n_unparseable_timestamps": report.n_unparseable_timestamps,
        "invalid_counts": report.invalid_counts,
        "missing_counts_raw": report.missing_counts,
        "n_daily_rows_before_drop": int(len(filled)),
        "n_processed_daily_rows": int(len(processed)),
        "n_train_days": int(len(train_df)),
        "n_val_days": int(len(val_df)),
        "n_test_days": int(len(test_df)),
        "n_train_windows": _n_windows(y_train),
        "n_val_windows": _n_windows(y_val),
        "n_test_windows": _n_windows(y_test),
        "missing_strategy": config.missing_strategy,
        "daily_aggregation": config.daily_aggregation,
        "scaler_fitted_on": "train_only",
        "unavailable_columns": list(unavailable),
        "available_columns": list(available),
        "train_target_dates": target_dates_for_windows(train_df.index, config.window_size),
        "val_target_dates": target_dates_for_windows(val_df.index, config.window_size),
        "test_target_dates": target_dates_for_windows(test_df.index, config.window_size),
        "notes": list(report.notes)
        + [
            "Split frames are physical units; X/y are scaled.",
            "Unavailable columns are not imputed and stay NaN in X/y.",
            "Windows are built inside each split so validation/test days never enter training windows.",
        ],
    }
    if _n_windows(y_val) == 0 or _n_windows(y_test) == 0 or _n_windows(y_train) == 0:
        diagnostics["notes"].append(
            "A split has fewer than window_size+1 days, so it produced zero windows. "
            "This is intentional (no cross-split leakage). Use more daily rows or a smaller window."
        )

    return PipelineResult(
        processed_df=processed,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        scalers=scaler,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        unavailable_columns=unavailable,
        column_availability={column: column in available for column in config.parameters},
        diagnostics=diagnostics,
        config=config,
        validation_report=report,
        univariate_windows=univariate,
    )


def _n_windows(y: np.ndarray | dict[str, np.ndarray]) -> int:
    if isinstance(y, dict):
        first = next(iter(y.values()))
        return int(len(first))
    return int(len(y))
