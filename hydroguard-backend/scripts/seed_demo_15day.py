#!/usr/bin/env python3
"""Seed and manage the 15-day simulated demonstration for the final EPICS review.

Creates and seeds node `demo_tank_15d` ("Hostel Demo Tank (15-Day Simulation)")
with 15 chronological daily observations and controlled demonstration alerts.
Clearly segregated with provenance `SIMULATED_DEMO`.

Usage:
    python scripts/seed_demo_15day.py             # Seed or refresh the 15-day dataset
    python scripts/seed_demo_15day.py --status    # Check current demo node status
    python scripts/seed_demo_15day.py --reset     # Clear and re-seed from scratch
    python scripts/seed_demo_15day.py --replay    # Step-by-step observation playback
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add backend root to path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.database import get_db_context
from app.db.models import Alert, Node, SensorReading
from app.db.repositories import NodeRepository, SensorReadingRepository

DEMO_NODE_ID = "demo_tank_15d"
DEMO_NODE_NAME = "Hostel Demo Tank (15-Day Simulation)"
DEMO_NODE_LOCATION = "Hostel Block A - Simulation Tank"
DEMO_SOURCE = "SIMULATED_DEMO"
CSV_PATH = BACKEND_ROOT / "data" / "demo_water_quality_15day.csv"


def load_demo_csv() -> list[dict[str, str]]:
    """Load the 15-day demo CSV dataset."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Demo CSV not found at {CSV_PATH}. Run data/generate_demo_water_quality_15day.py first."
        )
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def ensure_demo_node(db) -> Node:
    """Ensure the demo node exists and is online."""
    node = NodeRepository.get_or_create(
        db=db,
        node_id=DEMO_NODE_ID,
        name=DEMO_NODE_NAME,
        location=DEMO_NODE_LOCATION,
        status="online",
    )
    node.name = DEMO_NODE_NAME
    node.location = DEMO_NODE_LOCATION
    node.status = "online"
    db.commit()
    return node


def seed_demo_readings(db, rows: list[dict[str, str]]) -> int:
    """Insert the 15 demo readings into the database."""
    # Remove existing demo readings for this node
    db.query(SensorReading).filter(
        SensorReading.node_id == DEMO_NODE_ID,
        SensorReading.source == DEMO_SOURCE,
    ).delete(synchronize_session=False)

    inserted = 0
    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        reading = SensorReading(
            node_id=DEMO_NODE_ID,
            timestamp=ts,
            ph=float(row["ph"]),
            tds=float(row["tds"]),
            turbidity=float(row["turbidity"]),
            temperature=float(row["temperature"]),
            red=int(row["red"]) if row.get("red") else None,
            green=int(row.get("green")) if row.get("green") else None,
            blue=int(row.get("blue")) if row.get("blue") else None,
            clear=int(row.get("clear")) if row.get("clear") else None,
            optical_colour_index=float(row["optical_colour_index"]) if row.get("optical_colour_index") else None,
            source=DEMO_SOURCE,
        )
        db.add(reading)
        inserted += 1

    db.commit()
    return inserted


def seed_demo_alerts(db) -> int:
    """Seed the controlled EPICS demonstration alerts."""
    db.query(Alert).filter(Alert.node_id == DEMO_NODE_ID).delete(synchronize_session=False)

    alerts = [
        Alert(
            node_id=DEMO_NODE_ID,
            timestamp=datetime(2026, 10, 18, 14, 30, tzinfo=timezone.utc),
            parameter="turbidity",
            value=6.35,
            threshold=5.00,
            severity="CRITICAL",
            status="RESOLVED",
            message="Turbidity exceeded WHO/BIS permissible threshold of 5.0 NTU (measured 6.35 NTU) - sediment detected at inlet pipe.",
        ),
        Alert(
            node_id=DEMO_NODE_ID,
            timestamp=datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc),
            parameter="tds",
            value=542.00,
            threshold=500.00,
            severity="WARNING",
            status="RESOLVED",
            message="TDS exceeded 500 ppm desirable limit (measured 542 ppm) - mineral-rich water supply detected.",
        ),
        Alert(
            node_id=DEMO_NODE_ID,
            timestamp=datetime(2026, 10, 25, 12, 15, tzinfo=timezone.utc),
            parameter="ph",
            value=6.18,
            threshold=6.50,
            severity="WARNING",
            status="ACTIVE",
            message="pH dropped below safe minimum of 6.5 (measured 6.18) - water is slightly acidic due to atmospheric stagnation.",
        ),
    ]

    for a in alerts:
        db.add(a)

    db.commit()
    return len(alerts)


def show_status(db) -> None:
    """Print the current demo status."""
    node = NodeRepository.get_by_node_id(db, DEMO_NODE_ID)
    if not node:
        print(f"Demo node '{DEMO_NODE_ID}' is NOT registered in database.")
        return

    readings = (
        db.query(SensorReading)
        .filter(SensorReading.node_id == DEMO_NODE_ID, SensorReading.source == DEMO_SOURCE)
        .order_by(SensorReading.timestamp.asc())
        .all()
    )
    alerts = db.query(Alert).filter(Alert.node_id == DEMO_NODE_ID).all()

    print("=" * 60)
    print(f"HydroGuard Demo Node: {node.name} ({node.node_id})")
    print(f"Location: {node.location} | Status: {node.status}")
    print(f"Total Readings: {len(readings)} (Source: {DEMO_SOURCE})")
    if readings:
        first = readings[0]
        last = readings[-1]
        print(f"Timeline: {first.timestamp.isoformat()} to {last.timestamp.isoformat()}")
        print(f"Latest Reading: pH={last.ph}, TDS={last.tds} ppm, Turb={last.turbidity} NTU, Temp={last.temperature}°C, RGB=({last.red},{last.green},{last.blue})")

    print(f"\nDemonstration Alerts ({len(alerts)}):")
    for a in alerts:
        print(f"  [{a.severity} | {a.status}] {a.parameter.upper()}: {a.value} (threshold {a.threshold}) - {a.message}")
    print("=" * 60)


def replay_demo(db, rows: list[dict[str, str]], delay: float = 0.5) -> None:
    """Step-by-step playback simulation of demo observations."""
    print(f"Starting replay of {len(rows)} observations for {DEMO_NODE_ID} (delay={delay}s)...")
    db.query(SensorReading).filter(
        SensorReading.node_id == DEMO_NODE_ID,
        SensorReading.source == DEMO_SOURCE,
    ).delete(synchronize_session=False)
    db.commit()

    for i, row in enumerate(rows, 1):
        ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        reading = SensorReading(
            node_id=DEMO_NODE_ID,
            timestamp=ts,
            ph=float(row["ph"]),
            tds=float(row["tds"]),
            turbidity=float(row["turbidity"]),
            temperature=float(row["temperature"]),
            red=int(row["red"]) if row.get("red") else None,
            green=int(row.get("green")) if row.get("green") else None,
            blue=int(row.get("blue")) if row.get("blue") else None,
            clear=int(row.get("clear")) if row.get("clear") else None,
            optical_colour_index=float(row["optical_colour_index"]) if row.get("optical_colour_index") else None,
            source=DEMO_SOURCE,
        )
        db.add(reading)
        db.commit()
        print(f"  [{i}/{len(rows)}] Replayed: {row['timestamp']} | pH={row['ph']} | TDS={row['tds']} | Turb={row['turbidity']} | Condition={row['condition']}")
        if delay > 0 and i < len(rows):
            time.sleep(delay)

    print("Replay completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Seed and manage 15-day EPICS review demonstration.")
    parser.add_argument("--status", action="store_true", help="Show demo node status")
    parser.add_argument("--reset", action="store_true", help="Reset and re-seed from scratch")
    parser.add_argument("--replay", action="store_true", help="Run interactive replay simulation")
    parser.add_argument("--delay", type=float, default=0.3, help="Replay delay per step in seconds")
    args = parser.parse_args()

    rows = load_demo_csv()

    with get_db_context() as db:
        ensure_demo_node(db)

        if args.status:
            show_status(db)
            return

        if args.replay:
            replay_demo(db, rows, delay=args.delay)
            seed_demo_alerts(db)
            show_status(db)
            return

        # Default action or --reset
        readings_count = seed_demo_readings(db, rows)
        alerts_count = seed_demo_alerts(db)
        print(f"Successfully seeded {readings_count} readings and {alerts_count} demonstration alerts for {DEMO_NODE_ID}.")
        show_status(db)


if __name__ == "__main__":
    main()
