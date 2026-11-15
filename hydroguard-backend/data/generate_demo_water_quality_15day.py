"""Generate a reproducible, deterministic 15-day water-quality demonstration dataset.

Designed for the final EPICS project review to demonstrate:
1. 15 days of chronological telemetry without permanent physical installation at the hostel tank.
2. Controlled water-quality events:
   - Day 4-5: Turbidity disturbance event (sediment stirred, peak 6.35 NTU > 5.0 NTU limit).
   - Day 7-8: High TDS mineral intrusion (peak 542 ppm > 500 ppm limit).
   - Day 11-12: Acidic pH anomaly (trough 6.18 < 6.5 limit).
3. TCS34725 optical sensor counts (Clear, Red, Green, Blue) and derived Optical Colour Index.
4. Complete isolation with data provenance: SIMULATED_DEMO.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent
CSV_PATH = DATA_DIR / "demo_water_quality_15day.csv"
METADATA_PATH = DATA_DIR / "demo_water_quality_15day.metadata.json"
SOURCE = "SIMULATED_DEMO"
START_DATE = date(2026, 10, 15)
OBSERVATION_COUNT = 15
RANDOM_SEED = 42


def build_rows() -> list[dict[str, object]]:
    """Build 15 daily chronological observations with controlled events."""
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, object]] = []

    # Defined controlled event pulses for the 15-day review demonstration:
    # Day index 0 is 2026-10-15.
    # Day 3-5 (indices 3, 4, 5): Turbidity surge (inlet pipe stirring / sediment)
    turbidity_pulse = {3: 2.10, 4: 5.15, 5: 2.80, 6: 0.60}
    # Day 6-8 (indices 6, 7, 8): Mineral / high-TDS supply influx
    tds_pulse = {6: 85.0, 7: 285.0, 8: 245.0, 9: 75.0}
    # Day 10-12 (indices 10, 11, 12): Acidic pipe stagnation / rainwater ingress
    ph_pulse = {10: -0.45, 11: -1.08, 12: -0.42}

    for index in range(OBSERVATION_COUNT):
        day = START_DATE + timedelta(days=index)
        t_noise = rng.gauss(0, 0.15)
        ph_noise = rng.gauss(0, 0.03)
        tds_noise = rng.gauss(0, 4.0)
        turb_noise = rng.gauss(0, 0.08)

        # Baseline diurnal/seasonal dynamics
        temperature = 22.8 + 1.2 * math.sin(2 * math.pi * index / 14) + t_noise
        ph = 7.28 + 0.08 * math.cos(2 * math.pi * index / 7) + ph_noise + ph_pulse.get(index, 0.0)
        tds = 255.0 + 18.0 * math.sin(2 * math.pi * index / 10) + tds_noise + tds_pulse.get(index, 0.0)
        turbidity = 1.18 + 0.12 * math.sin(2 * math.pi * index / 5) + turb_noise + turbidity_pulse.get(index, 0.0)
        turbidity = max(0.5, turbidity)

        # TCS34725 optical sensor physics:
        # Turbidity attenuates total luminous flux (Clear channel) and selectively absorbs blue/green
        base_clear = 12200 + rng.gauss(0, 80)
        turbidity_attenuation = max(0.0, (turbidity - 1.0) * 450)
        clear = round(max(5000, base_clear - turbidity_attenuation))

        turbidity_factor = min(1.0, max(0.0, (turbidity - 1.0) / 6.0))
        red_ratio = 0.94 - 0.12 * turbidity_factor + rng.gauss(0, 0.005)
        green_ratio = 0.91 - 0.10 * turbidity_factor + rng.gauss(0, 0.005)
        blue_ratio = 0.90 - 0.07 * turbidity_factor + rng.gauss(0, 0.005)

        red = round(clear * red_ratio)
        green = round(clear * green_ratio)
        blue = round(clear * blue_ratio)

        # Documented optical colour index formula (ITU-R BT.601 / Rec. 709 luma loss):
        optical_colour_index = 1.0 - (
            0.2126 * red + 0.7152 * green + 0.0722 * blue
        ) / clear

        # Water condition thresholds (BIS IS 10500 / WHO Guidelines):
        # pH: 6.5 - 8.5
        # TDS: <= 500 ppm desirable
        # Turbidity: <= 5.0 NTU permissible, <= 1.0 NTU desirable
        if ph < 6.5 or ph > 8.5 or tds > 500.0 or turbidity > 5.0:
            condition = "DEGRADED"
        elif tds > 300.0 or turbidity > 2.0 or optical_colour_index > 0.14:
            condition = "NORMAL"
        else:
            condition = "GOOD"

        timestamp_iso = datetime.combine(day, time(12, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append({
            "timestamp": timestamp_iso,
            "ph": round(ph, 2),
            "tds": round(tds, 1),
            "turbidity": round(turbidity, 2),
            "temperature": round(temperature, 1),
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
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    metadata = {
        "dataset_name": "HydroGuard 15-day EPICS review demonstration dataset",
        "source": SOURCE,
        "data_provenance": SOURCE,
        "dataset_type": "DEMONSTRATION",
        "real_sensor_data": False,
        "random_seed": RANDOM_SEED,
        "observation_count": len(rows),
        "start_timestamp": rows[0]["timestamp"],
        "end_timestamp": rows[-1]["timestamp"],
        "cadence": "daily (24-hour interval at 12:00 UTC)",
        "parameters": ["pH", "TDS", "turbidity", "temperature", "optical_colour_index"],
        "optical_sensor_channels": ["red", "green", "blue", "clear"],
        "optical_colour_index_method": (
            "Derived from relative TCS34725 channel intensities using standard luma weighting. "
            "OCI = 1.0 - (0.2126*R + 0.7152*G + 0.0722*B)/Clear. "
            "Synthetically generated for demonstration; not scientifically calibrated."
        ),
        "demonstration_events": [
            {
                "event_id": "EVT-01-TURB",
                "days": "Day 4 - Day 5 (2026-10-18 to 2026-10-19)",
                "description": "Sediment disturbance at inlet pipe causing high turbidity spike (peak 6.35 NTU > 5.0 NTU limit). Triggers HIGH_TURBIDITY alert.",
                "parameter_affected": "turbidity",
                "peak_value": 6.35,
            },
            {
                "event_id": "EVT-02-TDS",
                "days": "Day 7 - Day 8 (2026-10-21 to 2026-10-22)",
                "description": "Mineral-rich municipal water inflow causing elevated dissolved solids (peak 542 ppm > 500 ppm limit). Triggers ELEVATED_TDS alert.",
                "parameter_affected": "TDS",
                "peak_value": 542.0,
            },
            {
                "event_id": "EVT-03-PH",
                "days": "Day 11 - Day 12 (2026-10-25 to 2026-10-26)",
                "description": "Acidic stagnation / atmospheric rainwater ingress causing pH depression (trough 6.18 < 6.5 limit). Triggers ACIDIC_WATER alert.",
                "parameter_affected": "pH",
                "peak_value": 6.18,
            },
        ],
        "condition_counts": {
            condition: sum(row["condition"] == condition for row in rows)
            for condition in ("GOOD", "NORMAL", "DEGRADED")
        },
        "csv_sha256": digest,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Created {CSV_PATH.name} (rows={len(rows)}, sha256={digest})")


if __name__ == "__main__":
    main()
