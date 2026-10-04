"""Unit tests for the shared HydroGuard ML data pipeline.

Fixtures are synthetic DEMO/TEST series. They are not real sensor measurements
and must not be reported as a real dataset.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.data.dataset import PipelineConfig, run_pipeline
from ml.data.loader import load_csv
from ml.data.preprocessing import chronological_split, collapse_duplicate_timestamps, sort_chronologically
from ml.data.validator import (
    REQUIRED_COLUMNS,
    detect_duplicate_timestamps,
    parse_timestamp_column,
    validate_raw_frame,
    validate_required_columns,
)
from ml.data.window_generator import assert_no_future_leakage, create_sliding_windows

DEMO_CSV = BACKEND_ROOT / "data" / "demo_water_quality.csv"


def synthetic_series(n_days: int = 40, start: str = "2026-01-01") -> pd.DataFrame:
    """Build a labeled synthetic frame (not real sensor data)."""
    index = pd.date_range(start, periods=n_days, freq="D", tz="UTC")
    day = np.arange(n_days, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": index,
            "pH": 7.0 + 0.02 * np.sin(day / 5.0),
            "TDS": 180.0 + day,
            "turbidity": 1.2 + 0.01 * day,
            "temperature": 22.0 + 0.05 * np.cos(day / 3.0),
        }
    )


class ColumnValidationTests(unittest.TestCase):
    def test_required_columns_detected(self) -> None:
        frame = pd.DataFrame({"timestamp": ["2026-01-01"], "pH": [7.0]})
        missing = validate_required_columns(frame)
        self.assertIn("TDS", missing)
        self.assertIn("turbidity", missing)

    def test_complete_columns_pass(self) -> None:
        frame = synthetic_series(5)
        self.assertEqual(validate_required_columns(frame), [])

    def test_missing_columns_raise_in_pipeline(self) -> None:
        frame = pd.DataFrame({"timestamp": ["2026-01-01T00:00:00Z"], "pH": [7.0]})
        with self.assertRaises(ValueError):
            run_pipeline(frame, PipelineConfig(window_size=2))


class TimestampParsingTests(unittest.TestCase):
    def test_parses_iso_z_and_naive(self) -> None:
        frame = pd.DataFrame({"timestamp": ["2026-01-01T10:00:00Z", "2026-01-02 11:00:00"]})
        parsed = parse_timestamp_column(frame)
        self.assertEqual(int(parsed.notna().sum()), 2)
        self.assertIsNotNone(parsed.dt.tz)

    def test_unparseable_becomes_nat(self) -> None:
        frame = pd.DataFrame({"timestamp": ["not-a-date", "2026-01-01"]})
        parsed = parse_timestamp_column(frame)
        self.assertTrue(pd.isna(parsed.iloc[0]))
        self.assertFalse(pd.isna(parsed.iloc[1]))


class ChronologicalSortingTests(unittest.TestCase):
    def test_rows_are_sorted_ascending(self) -> None:
        frame = synthetic_series(6).iloc[[5, 0, 3, 1, 4, 2]].reset_index(drop=True)
        parsed, _ = validate_raw_frame(frame)
        sorted_frame = sort_chronologically(parsed)
        deltas = sorted_frame["timestamp"].diff().dropna()
        self.assertTrue((deltas >= pd.Timedelta(0)).all())


class DuplicateHandlingTests(unittest.TestCase):
    def test_duplicate_timestamps_detected(self) -> None:
        stamps = pd.to_datetime(
            ["2026-01-01T10:00:00Z", "2026-01-01T10:00:00Z", "2026-01-02T10:00:00Z"],
            utc=True,
        )
        mask = detect_duplicate_timestamps(stamps)
        self.assertEqual(int(mask.sum()), 2)

    def test_duplicate_timestamps_collapsed_to_mean(self) -> None:
        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    ["2026-01-01T10:00:00Z", "2026-01-01T10:00:00Z"], utc=True
                ),
                "pH": [7.0, 8.0],
                "TDS": [100.0, 200.0],
                "turbidity": [1.0, 3.0],
                "temperature": [20.0, 22.0],
            }
        )
        collapsed = collapse_duplicate_timestamps(frame, how="mean")
        self.assertEqual(len(collapsed), 1)
        self.assertAlmostEqual(float(collapsed.loc[0, "pH"]), 7.5)
        self.assertAlmostEqual(float(collapsed.loc[0, "TDS"]), 150.0)


class SplitTests(unittest.TestCase):
    def test_chronological_70_15_15(self) -> None:
        daily = synthetic_series(100).set_index("timestamp")[["pH", "TDS", "turbidity", "temperature"]]
        train_df, val_df, test_df = chronological_split(daily, 0.70, 0.15, 0.15)
        self.assertEqual(len(train_df), 70)
        self.assertEqual(len(val_df), 15)
        self.assertEqual(len(test_df), 15)
        self.assertLess(train_df.index.max(), val_df.index.min())
        self.assertLess(val_df.index.max(), test_df.index.min())

    def test_random_split_is_not_used(self) -> None:
        daily = synthetic_series(20).set_index("timestamp")[["pH", "TDS", "turbidity", "temperature"]]
        train_df, val_df, test_df = chronological_split(daily, 0.50, 0.25, 0.25)
        combined = pd.concat([train_df, val_df, test_df])
        pd.testing.assert_index_equal(combined.index, daily.index)


class ScalerAndWindowTests(unittest.TestCase):
    def test_scaler_fits_only_on_training_data(self) -> None:
        frame = synthetic_series(40)
        # Make later days much larger so a full-series fit would differ.
        frame.loc[28:, "TDS"] = frame.loc[28:, "TDS"] + 5000.0
        result = run_pipeline(
            frame,
            PipelineConfig(window_size=3, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15),
        )
        tds_index = list(result.scalers.available_columns).index("TDS")
        train_mean = float(result.train_df["TDS"].mean())
        full_mean = float(result.processed_df["TDS"].mean())
        fitted_mean = float(result.scalers._scaler.mean_[tds_index])
        self.assertAlmostEqual(fitted_mean, train_mean, places=6)
        self.assertNotAlmostEqual(fitted_mean, full_mean, places=2)

    def test_window_shapes_multivariate(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15),
        )
        n_train = len(result.train_df) - 3
        self.assertEqual(result.X_train.shape, (n_train, 3, 4))
        self.assertEqual(result.y_train.shape, (n_train, 4))
        self.assertEqual(result.X_train.shape[2], 4)
        self.assertEqual(result.y_train.shape[1], 4)

    def test_no_future_leakage_in_windows(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15),
        )
        scaled = result.scalers.transform(result.train_df)
        assert_no_future_leakage(scaled, result.X_train, result.y_train, 3)
        for i in range(len(result.y_train)):
            np.testing.assert_allclose(result.X_train[i], scaled[i : i + 3], equal_nan=True)
            np.testing.assert_allclose(result.y_train[i], scaled[i + 3], equal_nan=True)
            last_input_day = result.train_df.index[i + 2]
            target_day = result.train_df.index[i + 3]
            self.assertEqual(target_day, last_input_day + pd.Timedelta(days=1))

    def test_windows_do_not_cross_split_boundaries(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15),
        )
        last_train = result.train_df.index.max()
        first_val = result.val_df.index.min()
        self.assertLess(last_train, first_val)
        train_target_dates = result.diagnostics["train_target_dates"]
        self.assertTrue((train_target_dates <= last_train).all())

    def test_ml_contract_is_four_checkpoint_parameters(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3),
        )
        self.assertEqual(tuple(result.config.parameters), ("pH", "TDS", "turbidity", "temperature"))

    def test_inverse_transform_roundtrip_available_columns(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3),
        )
        restored = result.inverse_transform_predictions(result.y_train)
        original = result.train_df[["pH", "TDS", "turbidity", "temperature"]].to_numpy()[3:]
        np.testing.assert_allclose(restored[:, :4], original, rtol=1e-6, atol=1e-6)

    def test_univariate_shapes(self) -> None:
        result = run_pipeline(
            synthetic_series(40),
            PipelineConfig(window_size=3, mode="univariate"),
        )
        self.assertIsInstance(result.X_train, dict)
        self.assertEqual(result.X_train["pH"].shape[1:], (3, 1))
        self.assertEqual(result.y_train["pH"].shape[1], 1)

    def test_invalid_ph_becomes_nan_not_fabricated(self) -> None:
        frame = synthetic_series(20)
        frame.loc[5, "pH"] = 99.0
        _, report = validate_raw_frame(frame)
        self.assertGreaterEqual(report.invalid_counts["pH"], 1)


class LoaderDemoCsvTests(unittest.TestCase):
    def test_demo_csv_is_explicitly_demo_provenance_and_model_inputs_are_four(self) -> None:
        frame = load_csv(DEMO_CSV)
        for column in REQUIRED_COLUMNS:
            self.assertIn(column, frame.columns)
        result = run_pipeline(
            DEMO_CSV,
            PipelineConfig(window_size=2, train_ratio=0.50, val_ratio=0.25, test_ratio=0.25),
        )
        self.assertEqual(result.diagnostics["available_columns"], ["pH", "TDS", "turbidity", "temperature"])
        self.assertGreater(result.validation_report.n_duplicate_timestamps, 0)
        self.assertGreater(result.validation_report.invalid_counts["pH"], 0)


class DirectWindowUnitTests(unittest.TestCase):
    def test_create_sliding_windows_shapes(self) -> None:
        values = np.arange(20, dtype=float).reshape(10, 2)
        X, y = create_sliding_windows(values, window_size=4)
        self.assertEqual(X.shape, (6, 4, 2))
        self.assertEqual(y.shape, (6, 2))
        np.testing.assert_array_equal(X[0], values[0:4])
        np.testing.assert_array_equal(y[0], values[4])


if __name__ == "__main__":
    unittest.main()
