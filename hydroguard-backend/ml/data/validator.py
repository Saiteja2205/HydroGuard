"""Validation helpers for raw HydroGuard water-quality tables."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Active forecasting contract. Optical colour remains experimental, but is an
# explicit model feature only for clearly labelled development datasets.
PARAMETERS: tuple[str, ...] = (
    "pH",
    "TDS",
    "turbidity",
    "temperature",
    "optical_colour_index",
)
PRODUCT_PARAMETERS: tuple[str, ...] = PARAMETERS
DEPRECATED_LEGACY_PARAMETERS: tuple[str, ...] = ("EC", "DO", "ORP", "nitrate", "ammonia", "flow_rate")
REQUIRED_COLUMNS: tuple[str, ...] = ("timestamp",) + PARAMETERS

# Bounds for obviously invalid readings. Out-of-range values become NaN.
# They are not replaced with fabricated sensor measurements.
VALID_RANGES: dict[str, tuple[float, float]] = {
    "pH": (0.0, 14.0),
    "TDS": (0.0, 100_000.0),
    "turbidity": (0.0, 10_000.0),
    "temperature": (-20.0, 80.0),
    "optical_colour_index": (0.0, 1.0),
}


@dataclass
class ValidationReport:
    n_rows: int
    missing_required_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    n_unparseable_timestamps: int = 0
    n_duplicate_timestamps: int = 0
    duplicate_timestamp_values: list[str] = field(default_factory=list)
    missing_counts: dict[str, int] = field(default_factory=dict)
    invalid_counts: dict[str, int] = field(default_factory=dict)
    all_missing_columns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok_columns(self) -> bool:
        return not self.missing_required_columns


def validate_required_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in REQUIRED_COLUMNS if column not in frame.columns]


def parse_timestamp_column(frame: pd.DataFrame, column: str = "timestamp") -> pd.Series:
    """Parse timestamps to UTC. Unparseable values become NaT."""
    if column not in frame.columns:
        raise ValueError(f"Missing timestamp column: {column}")
    return pd.to_datetime(frame[column], utc=True, errors="coerce", format="mixed")


def detect_duplicate_timestamps(timestamps: pd.Series) -> pd.Series:
    """Return the timestamp series mask of duplicated (non-NaT) values."""
    valid = timestamps.notna()
    duplicated = timestamps.duplicated(keep=False) & valid
    return duplicated


def detect_missing_values(frame: pd.DataFrame, columns: tuple[str, ...] = PARAMETERS) -> dict[str, int]:
    return {column: int(frame[column].isna().sum()) for column in columns if column in frame.columns}


def flag_invalid_numeric_values(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Coerce parameter columns to numeric and set out-of-range values to NaN."""
    cleaned = frame.copy()
    invalid_counts: dict[str, int] = {}
    for column, (lower, upper) in VALID_RANGES.items():
        if column not in cleaned.columns:
            continue
        numeric = pd.to_numeric(cleaned[column], errors="coerce")
        out_of_range = numeric.notna() & ((numeric < lower) | (numeric > upper))
        invalid_counts[column] = int(out_of_range.sum())
        numeric = numeric.mask(out_of_range)
        cleaned[column] = numeric
    return cleaned, invalid_counts


def validate_raw_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, ValidationReport]:
    """Validate columns, parse time, sort later in preprocessing.

    Returns a copy with parsed timestamps and numeric parameters. Duplicate
    rows are reported but not dropped here.
    """
    missing_required = validate_required_columns(frame)
    if missing_required:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_required)
            + f". Expected: {', '.join(REQUIRED_COLUMNS)}"
        )

    working = frame.copy()
    extra = [column for column in working.columns if column not in REQUIRED_COLUMNS]
    timestamps = parse_timestamp_column(working)
    n_unparseable = int(timestamps.isna().sum())
    if n_unparseable == len(working):
        raise ValueError("No parseable timestamps in the timestamp column.")

    working["timestamp"] = timestamps
    duplicate_mask = detect_duplicate_timestamps(working["timestamp"])
    duplicate_values = (
        working.loc[duplicate_mask, "timestamp"]
        .dropna()
        .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        .drop_duplicates()
        .tolist()
    )

    working, invalid_counts = flag_invalid_numeric_values(working)
    missing_counts = detect_missing_values(working)
    all_missing = [column for column, count in missing_counts.items() if count == len(working)]

    notes: list[str] = []
    if all_missing:
        notes.append(
            "Columns with no numeric values (unavailable, not fabricated): "
            + ", ".join(all_missing)
        )
    if extra:
        notes.append("Extra columns were ignored: " + ", ".join(extra))

    report = ValidationReport(
        n_rows=len(working),
        extra_columns=extra,
        n_unparseable_timestamps=n_unparseable,
        n_duplicate_timestamps=int(duplicate_mask.sum()),
        duplicate_timestamp_values=duplicate_values,
        missing_counts=missing_counts,
        invalid_counts=invalid_counts,
        all_missing_columns=all_missing,
        notes=notes,
    )
    return working, report
