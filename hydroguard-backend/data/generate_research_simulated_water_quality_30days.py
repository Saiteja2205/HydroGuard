"""Generate a 30-day simulated water-quality dataset for ICETICS 2027 research experiments.

Provides an explicitly labeled, synthetic 30-day chronological dataset
(source: SIMULATED_RESEARCH) designed for controlled algorithmic benchmarking.

Key physical and chemical dynamics modeled:
1. Seasonal and diurnal temperature drift.
2. Dissociation equilibrium coupling between temperature and pH.
3. Gradual mineral accumulation and precipitation dilution dynamics for TDS.
4. Rainfall runoff events and subsequent settling curves for Turbidity.
5. Multi-channel TCS34725 optical sensor physics (Clear, Red, Green, Blue) and
   derived Optical Colour Index (OCI).
6. Controlled sensor noise and realistic measurement variance.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

BACKEND_DATA_DIR = Path(__file__).resolve().parent
RESEARCH_DIR = BACKEND_DATA_DIR.parents[1] / "research" / "ICETICS_2027"

CSV_FILENAME = "research_simulated_water_quality_30days.csv"
METADATA_FILENAME = "research_simulated_water_quality_30days.metadata.json"

CSV_PATH = BACKEND_DATA_DIR / CSV_FILENAME
METADATA_PATH = BACKEND_DATA_DIR / METADATA_FILENAME

SOURCE = "SIMULATED_RESEARCH"
START_DATE = date(2026, 9, 1)
OBSERVATION_COUNT = 30
RANDOM_SEED = 12345


def build_rows() -> list[dict[str, object]]:
    """Build 30 daily chronological observations with realistic physical coupling."""
    rng = random.Random(RANDOM_SEED)
    rows: list[dict[str, object]] = []

    # Runoff disturbance event around day 21-23 (indices 20, 21, 22)
    runoff_turbidity = {20: 1.85, 21: 4.10, 22: 2.70, 23: 1.10}
    dilution_tds = {20: -25.0, 21: -65.0, 22: -45.0, 23: -15.0}

    for index in range(OBSERVATION_COUNT):
        day = START_DATE + timedelta(days=index)

        # 1. Temperature: seasonal downward trend from September 1 to 30
        temp_trend = 24.5 - (index / 30.0) * 2.2
        temp_cycle = 0.9 * math.sin(2 * math.pi * index / 15)
        temp_noise = rng.gauss(0, 0.12)
        temperature = temp_trend + temp_cycle + temp_noise

        # 2. pH: coupled weakly to temperature (higher temp lowers neutral point)
        ph_temp_coupling = -0.015 * (temperature - 23.0)
        ph_drift = 0.08 * math.cos(2 * math.pi * index / 10)
        ph_noise = rng.gauss(0, 0.025)
        ph = 7.32 + ph_temp_coupling + ph_drift + ph_noise

        # 3. TDS: baseline 245 ppm, gradual mineral accumulation until day 19, then dilution event
        tds_accumulation = (index / 20.0) * 45.0 if index < 20 else 45.0 - ((index - 20) / 10.0) * 20.0
        tds_noise = rng.gauss(0, 3.2)
        tds = 245.0 + tds_accumulation + dilution_tds.get(index, 0.0) + tds_noise

        # 4. Turbidity: baseline ~1.05 NTU with runoff event on days 20-23
        turb_noise = rng.gauss(0, 0.06)
        turbidity = 1.05 + 0.10 * math.sin(2 * math.pi * index / 6) + turb_noise + runoff_turbidity.get(index, 0.0)
        turbidity = max(0.4, turbidity)

        # 5. TCS34725 Optical counts
        base_clear = 12150 + rng.gauss(0, 75)
        clear_attenuation = max(0.0, (turbidity - 1.0) * 480)
        clear = round(max(5000, base_clear - clear_attenuation))

        turb_factor = min(1.0, max(0.0, (turbidity - 1.0) / 5.0))
        red_ratio = 0.945 - 0.11 * turb_factor + rng.gauss(0, 0.004)
        green_ratio = 0.915 - 0.09 * turb_factor + rng.gauss(0, 0.004)
        blue_ratio = 0.905 - 0.06 * turb_factor + rng.gauss(0, 0.004)

        red = round(clear * red_ratio)
        green = round(clear * green_ratio)
        blue = round(clear * blue_ratio)

        # Optical Colour Index
        oci = 1.0 - (0.2126 * red + 0.7152 * green + 0.0722 * blue) / clear

        # Condition
        if ph < 6.5 or ph > 8.5 or tds > 500.0 or turbidity > 5.0:
            condition = "DEGRADED"
        elif tds > 300.0 or turbidity > 2.0 or oci > 0.14:
            condition = "NORMAL"
        else:
            condition = "GOOD"

        ts_iso = datetime.combine(day, time(12, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append({
            "timestamp": ts_iso,
            "ph": round(ph, 2),
            "tds": round(tds, 1),
            "turbidity": round(turbidity, 2),
            "temperature": round(temperature, 1),
            "red": red,
            "green": green,
            "blue": blue,
            "clear": clear,
            "optical_colour_index": round(oci, 5),
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
        "dataset_name": "HydroGuard 30-day ICETICS 2027 research simulated water-quality dataset",
        "source": SOURCE,
        "data_provenance": SOURCE,
        "dataset_type": "RESEARCH_SIMULATION",
        "real_sensor_data": False,
        "random_seed": RANDOM_SEED,
        "observation_count": len(rows),
        "start_timestamp": rows[0]["timestamp"],
        "end_timestamp": rows[-1]["timestamp"],
        "cadence": "daily (24-hour interval at 12:00 UTC)",
        "parameters": ["pH", "TDS", "turbidity", "temperature", "optical_colour_index"],
        "optical_sensor_channels": ["red", "green", "blue", "clear"],
        "optical_colour_index_method": (
            "Derived from TCS34725 RGB and Clear channels using standard luma formulation: "
            "OCI = 1.0 - (0.2126*R + 0.7152*G + 0.0722*B)/Clear. "
            "Simulated research metric for multi-modal evaluation."
        ),
        "modeling_assumptions": [
            "Temperature undergoes seasonal decay (-2.2°C across September) with diurnal oscillation.",
            "pH exhibits weak negative coupling with temperature based on dissociation equilibrium.",
            "TDS exhibits gradual mineral build-up punctuated by a precipitation runoff dilution event.",
            "Turbidity exhibits low baseline (1.05 NTU) with runoff event (peak 4.10 NTU on Day 22).",
            "Clear channel flux is attenuated by particulate scattering inversely proportional to turbidity."
        ],
        "condition_counts": {
            condition: sum(row["condition"] == condition for row in rows)
            for condition in ("GOOD", "NORMAL", "DEGRADED")
        },
        "csv_sha256": digest,
    }

    metadata_text = json.dumps(metadata, indent=2) + "\n"
    METADATA_PATH.write_text(metadata_text, encoding="utf-8")

    # Also mirror into research/ICETICS_2027/
    if RESEARCH_DIR.exists():
        research_csv = RESEARCH_DIR / CSV_FILENAME
        research_meta = RESEARCH_DIR / METADATA_FILENAME
        shutil.copyfile(CSV_PATH, research_csv)
        research_meta.write_text(metadata_text, encoding="utf-8")
        print(f"Mirrored to {research_csv}")

    print(f"Created {CSV_PATH.name} (rows={len(rows)}, sha256={digest})")


if __name__ == "__main__":
    main()
