"""Generate a deterministic, explicitly simulated 30-day water-quality dataset."""

import csv
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent
CSV_PATH = DATA_DIR / "development_water_quality_30day.csv"
METADATA_PATH = DATA_DIR / "development_water_quality_30day.metadata.json"
SOURCE = "SIMULATED_DEVELOPMENT"
START_DATE = date(2026, 9, 7)
OBSERVATION_COUNT = 30


def _pulse(index: int, points: dict[int, float]) -> float:
    return points.get(index, 0.0)


def build_rows() -> list[dict[str, object]]:
    """Build 30 daily observations with gradual events and recovery periods."""
    first_event = {12: 0.45, 13: 0.82, 14: 1.0, 15: 0.72, 16: 0.48, 17: 0.28, 18: 0.12}
    second_event = {25: 0.28, 26: 0.62, 27: 0.92, 28: 0.58, 29: 0.24}
    tds_rise = {7: 35, 8: 70, 9: 105, 10: 140, 11: 175}
    tds_event = {25: 235, 26: 295, 27: 315, 28: 170, 29: 85}
    rows: list[dict[str, object]] = []

    for index in range(OBSERVATION_COUNT):
        first = _pulse(index, first_event)
        second = _pulse(index, second_event)
        event = max(first, second)
        day = START_DATE + timedelta(days=index)

        # Slow temperature changes and small repeatable day-to-day variation.
        temperature = 23.1 + 1.1 * math.sin(2 * math.pi * index / 15) + 0.25 * math.sin(index / 3.2)
        ph = 7.22 + 0.12 * math.sin(2 * math.pi * index / 10) + 0.035 * math.sin(index / 2.7) - 0.32 * first - 0.58 * second
        tds = 185 + 16 * math.sin(2 * math.pi * index / 12) + 7 * math.cos(index / 3.5)
        tds += tds_rise.get(index, 0) + tds_event.get(index, 0)

        turbidity = 1.15 + 0.16 * (1 + math.sin(2 * math.pi * index / 8)) + 5.45 * first + 2.75 * second
        clear = round(12_000 + 850 * math.sin(2 * math.pi * index / 11) + 650 * event)
        colour_fraction = min(1.0, max(0.0, (turbidity - 1.45) / 5.6))
        red_ratio = 0.94 - 0.13 * colour_fraction
        green_ratio = 0.92 - 0.09 * colour_fraction
        blue_ratio = 0.91 - 0.055 * colour_fraction
        red = round(clear * red_ratio)
        green = round(clear * green_ratio)
        blue = round(clear * blue_ratio)
        optical_colour_index = 1 - (
            0.2126 * red + 0.7152 * green + 0.0722 * blue
        ) / clear

        if ph < 6.5 or ph > 8.5 or tds > 500 or turbidity > 5:
            condition = "DEGRADED"
        elif tds > 300 or turbidity > 2.5 or optical_colour_index > 0.12:
            condition = "NORMAL"
        else:
            condition = "GOOD"

        rows.append({
            "timestamp": datetime.combine(day, time(12), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ph": round(ph, 2),
            "tds": round(tds, 2),
            "turbidity": round(turbidity, 2),
            "temperature": round(temperature, 2),
            "red": red,
            "green": green,
            "blue": blue,
            "clear": clear,
            "optical_colour_index": round(optical_colour_index, 5),
            "source": SOURCE,
            "data_provenance": SOURCE,
            "condition": condition,
        })
    return rows


def main() -> None:
    rows = build_rows()
    fields = list(rows[0])
    with CSV_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    metadata = {
        "dataset_name": "HydroGuard 30-day development water-quality dataset",
        "source": SOURCE,
        "data_provenance": SOURCE,
        "dataset_type": "DEVELOPMENT",
        "real_sensor_data": False,
        "observation_count": len(rows),
        "start_timestamp": rows[0]["timestamp"],
        "end_timestamp": rows[-1]["timestamp"],
        "frequency": "daily",
        "parameters": ["pH", "TDS", "turbidity", "temperature", "optical_colour_index"],
        "raw_optical_sensor_fields": ["red", "green", "blue", "clear"],
        "optical_colour_index_method": (
            "Derived from normalized RGB channel intensity using a fixed luma weighting. "
            "Synthetic development relationship only; not sensor-calibrated or a scientific validity claim."
        ),
        "generation_method": "Deterministic smooth baseline, independent TDS drift, two quality events, and recovery periods.",
        "condition_counts": {condition: sum(row["condition"] == condition for row in rows) for condition in ("GOOD", "NORMAL", "DEGRADED")},
        "csv_sha256": digest,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"created={CSV_PATH.name} rows={len(rows)} sha256={digest}")


if __name__ == "__main__":
    main()
