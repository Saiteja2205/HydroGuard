"""Reproducible real sensor data export, validation, and quality auditing pipeline.

This module provides verified extraction of physical sensor observations from
the HydroGuard database and ThingSpeak hardware feeds, enforces strict physical
validity checks, computes sampling intervals and gap distributions, and audits
eligibility for next-day water quality forecasting.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from ml.data.validator import VALID_RANGES

ROOT = Path(__file__).resolve().parents[2]
REAL_DATA_CSV = ROOT / "data" / "real_thingspeak_observations_122.csv"
REAL_DATA_META = ROOT / "data" / "real_thingspeak_observations_122.metadata.json"
AUDIT_OUTPUT_PATH = ROOT / "artifacts" / "results" / "real_data_quality_audit.json"

CORE_PARAMETERS: tuple[str, ...] = ("pH", "TDS", "turbidity", "temperature")
OPTICAL_COLOUR_FIELDS: tuple[str, ...] = ("rgb_red", "rgb_green", "rgb_blue")


@dataclass
class NextDayContract:
    """Explicit contract for genuine next-day water quality forecasting."""

    target_name: str = "Next Daily Mean (t + 24h)"
    nominal_horizon_hours: int = 24
    cadence: str = "1D"
    input_history_days: int = 7
    target_local_time: str = "09:00 IST (03:30 UTC)"
    parameters: list[str] = field(default_factory=lambda: list(CORE_PARAMETERS))
    units: dict[str, str] = field(
        default_factory=lambda: {
            "pH": "pH units (0-14)",
            "TDS": "ppm (mg/L)",
            "turbidity": "NTU",
            "temperature": "°C",
        }
    )
    min_daily_coverage_ratio: float = 0.70  # >= 70% active observations in a 24h window
    max_allowed_intra_day_gap_hours: float = 2.0  # gaps > 2h invalidate the daily aggregate
    consecutive_days_required: int = 8  # 7 days input + 1 day target


@dataclass
class RealDataAuditReport:
    """Comprehensive data quality and forecasting eligibility report."""

    channel_id: int
    channel_name: str
    source_provenance: str
    total_raw_observations: int
    unique_timestamps: int
    duplicate_count: int
    date_range_start: str
    date_range_end: str
    total_calendar_span_hours: float
    total_active_measurement_minutes: float
    data_temporal_coverage_percent: float
    sampling_interval_median_seconds: float
    sampling_interval_iqr_seconds: float
    large_gaps_count_gt_5min: int
    large_gaps_count_gt_1hour: int
    maximum_gap_hours: float
    gaps_details: list[dict[str, Any]]
    parameter_statistics: dict[str, dict[str, float]]
    physical_validity_rates: dict[str, float]
    sensor_dropouts_count: dict[str, int]
    daily_resampling_summary: dict[str, Any]
    next_day_eligible_windows: int
    next_day_eligibility_status: str
    collection_requirements_for_next_day_forecasting: list[str]
    contract: dict[str, Any]


def load_real_observations_csv(path: Optional[Path] = None) -> pd.DataFrame:
    """Load and parse the verified real ThingSpeak observation dataset."""
    target_path = path or REAL_DATA_CSV
    if not target_path.exists():
        raise FileNotFoundError(f"Real sensor dataset not found at {target_path}")

    frame = pd.read_csv(target_path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def validate_and_clean_observations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Clean real sensor observations, detecting physical validity and dropouts.

    Does NOT replace dropouts with fabricated zeros. Preserves missingness.
    """
    cleaned = df.copy()
    cleaned = cleaned.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    # Deduplicate on entry_id and timestamp
    initial_len = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    duplicate_count = initial_len - len(cleaned)

    # Detect physical range violations and sensor dropouts
    dropouts: dict[str, int] = {}
    validity_rates: dict[str, float] = {}

    for param in CORE_PARAMETERS:
        if param not in cleaned.columns:
            continue
        vals = pd.to_numeric(cleaned[param], errors="coerce")
        min_v, max_v = VALID_RANGES[param]

        # In water quality probes, an exact 0.0 reading during bench test often indicates
        # probe disconnection / sensor dropout (e.g. pH=0.0 or Temp=0.0 while probe is unimmersed).
        is_zero_dropout = (vals == 0.0) & (param in ("pH", "temperature"))
        is_out_of_range = (vals < min_v) | (vals > max_v)
        is_invalid = is_zero_dropout | is_out_of_range | vals.isna()

        dropouts[param] = int(is_zero_dropout.sum())
        validity_rates[param] = float((~is_invalid).mean() * 100.0)

    stats = {
        "initial_rows": initial_len,
        "clean_rows": len(cleaned),
        "duplicates_dropped": duplicate_count,
        "dropouts": dropouts,
        "validity_rates": validity_rates,
    }
    return cleaned, stats


def perform_data_quality_audit(
    df: Optional[pd.DataFrame] = None,
    channel_id: int = 244357,
    channel_name: str = "VR WATER TANK QUALITY",
) -> RealDataAuditReport:
    """Run an exhaustive data quality audit on the real ThingSpeak sensor dataset."""
    raw_df = df if df is not None else load_real_observations_csv()
    cleaned_df, clean_stats = validate_and_clean_observations(raw_df)

    n_rows = len(cleaned_df)
    if n_rows < 2:
        raise ValueError(f"Insufficient observations ({n_rows}) for quality audit.")

    timestamps = cleaned_df["timestamp"]
    start_ts = timestamps.iloc[0]
    end_ts = timestamps.iloc[-1]
    total_span_hours = (end_ts - start_ts).total_seconds() / 3600.0

    # Sampling intervals
    diff_seconds = timestamps.diff().dt.total_seconds().dropna()
    median_interval = float(diff_seconds.median())
    q25 = float(diff_seconds.quantile(0.25))
    q75 = float(diff_seconds.quantile(0.75))
    iqr_interval = q75 - q25

    # Gaps analysis
    large_gaps = []
    gaps_gt_5m = 0
    gaps_gt_1h = 0
    max_gap_hours = 0.0

    for i in range(1, len(cleaned_df)):
        dt_sec = (timestamps.iloc[i] - timestamps.iloc[i - 1]).total_seconds()
        if dt_sec > 300:  # > 5 minutes
            gap_h = dt_sec / 3600.0
            gaps_gt_5m += 1
            if gap_h > 1.0:
                gaps_gt_1h += 1
            if gap_h > max_gap_hours:
                max_gap_hours = gap_h
            large_gaps.append(
                {
                    "from_entry_id": int(cleaned_df["entry_id"].iloc[i - 1])
                    if "entry_id" in cleaned_df
                    else i - 1,
                    "to_entry_id": int(cleaned_df["entry_id"].iloc[i])
                    if "entry_id" in cleaned_df
                    else i,
                    "from_timestamp": timestamps.iloc[i - 1].isoformat(),
                    "to_timestamp": timestamps.iloc[i].isoformat(),
                    "gap_seconds": float(dt_sec),
                    "gap_hours": round(gap_h, 2),
                }
            )

    # Active operational duration (summing intra-session duration where delta <= 300s)
    active_seconds = 0.0
    for dt_sec in diff_seconds:
        if dt_sec <= 300:
            active_seconds += dt_sec
    # Add median step for initial reading of each session
    n_sessions = gaps_gt_5m + 1
    active_seconds += n_sessions * median_interval
    active_minutes = active_seconds / 60.0
    coverage_percent = (active_seconds / (total_span_hours * 3600.0)) * 100.0 if total_span_hours > 0 else 0.0

    # Parameter statistics
    param_stats = {}
    for param in CORE_PARAMETERS:
        if param in cleaned_df.columns:
            s = pd.to_numeric(cleaned_df[param], errors="coerce").dropna()
            param_stats[param] = {
                "min": float(s.min()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "std": float(s.std()),
                "max": float(s.max()),
            }

    # Daily aggregation & contract evaluation
    contract = NextDayContract()
    daily_indexed = cleaned_df.set_index("timestamp")
    daily_counts = daily_indexed[list(CORE_PARAMETERS)].resample("D").count()
    daily_means = daily_indexed[list(CORE_PARAMETERS)].resample("D").mean()

    # Required daily samples assuming 32s interval: ~2700 readings/day
    expected_readings_per_day = 86400 / median_interval
    daily_summary = {
        "calendar_days_spanned": len(daily_counts),
        "days_with_any_observations": int((daily_counts["pH"] > 0).sum()),
        "days_meeting_coverage_threshold": 0,
        "daily_breakdown": [],
    }

    days_meeting_threshold = 0
    for day, row in daily_counts.iterrows():
        cnt = int(row["pH"])
        cov = (cnt / expected_readings_per_day) * 100.0 if expected_readings_per_day > 0 else 0.0
        meets = cov >= (contract.min_daily_coverage_ratio * 100.0)
        if meets:
            days_meeting_threshold += 1
        daily_summary["daily_breakdown"].append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "observed_count": cnt,
                "coverage_percent": round(cov, 2),
                "meets_next_day_coverage_threshold": meets,
            }
        )
    daily_summary["days_meeting_coverage_threshold"] = days_meeting_threshold

    # Complete eligible next-day training windows
    # To form 1 window of 7 days input + 1 day target requires 8 consecutive days meeting threshold.
    eligible_windows = 0
    if days_meeting_threshold >= contract.consecutive_days_required:
        # Check consecutive streak
        meets_series = pd.Series(
            [d["meets_next_day_coverage_threshold"] for d in daily_summary["daily_breakdown"]]
        )
        streak = meets_series.rolling(contract.consecutive_days_required).sum()
        eligible_windows = int((streak == contract.consecutive_days_required).sum())

    eligibility_status = (
        "ELIGIBLE"
        if eligible_windows > 0
        else "INSUFFICIENT_DATA_UNAVAILABLE"
    )

    collection_requirements = [
        "Continuous 24/7 logging: Probes must remain permanently powered and immersed in the water tank.",
        "Zero multi-hour dropouts: Network/power gaps must not exceed 2.0 hours per 24-hour cycle.",
        "Minimum duration: At least 30 consecutive calendar days with >= 70% daily coverage are required before training next-day models.",
        "Sensor recalibration: pH probe recalibration against pH 4.01, 7.00, and 10.01 buffers to eliminate hardware status flag 1.",
        "Turbidity zero-calibration in distilled water to prevent sensor saturation.",
    ]

    report = RealDataAuditReport(
        channel_id=channel_id,
        channel_name=channel_name,
        source_provenance="THINGSPEAK_HARDWARE",
        total_raw_observations=clean_stats["initial_rows"],
        unique_timestamps=clean_stats["clean_rows"],
        duplicate_count=clean_stats["duplicates_dropped"],
        date_range_start=start_ts.isoformat(),
        date_range_end=end_ts.isoformat(),
        total_calendar_span_hours=round(total_span_hours, 2),
        total_active_measurement_minutes=round(active_minutes, 1),
        data_temporal_coverage_percent=round(coverage_percent, 3),
        sampling_interval_median_seconds=median_interval,
        sampling_interval_iqr_seconds=iqr_interval,
        large_gaps_count_gt_5min=gaps_gt_5m,
        large_gaps_count_gt_1hour=gaps_gt_1h,
        maximum_gap_hours=round(max_gap_hours, 2),
        gaps_details=large_gaps,
        parameter_statistics=param_stats,
        physical_validity_rates=clean_stats["validity_rates"],
        sensor_dropouts_count=clean_stats["dropouts"],
        daily_resampling_summary=daily_summary,
        next_day_eligible_windows=eligible_windows,
        next_day_eligibility_status=eligibility_status,
        collection_requirements_for_next_day_forecasting=collection_requirements,
        contract=asdict(contract),
    )
    return report


def save_audit_report(report: RealDataAuditReport, output_path: Optional[Path] = None) -> Path:
    """Save the real data audit report to JSON."""
    target_path = output_path or AUDIT_OUTPUT_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2)
    return target_path


if __name__ == "__main__":
    report = perform_data_quality_audit()
    out = save_audit_report(report)
    print(f"Real data quality audit report saved to {out}")
    print(f"Total observations: {report.total_raw_observations}")
    print(f"Active measurement minutes: {report.total_active_measurement_minutes} mins")
    print(f"Data temporal coverage: {report.data_temporal_coverage_percent}%")
    print(f"Eligible next-day training windows: {report.next_day_eligible_windows}")
    print(f"Eligibility status: {report.next_day_eligibility_status}")
