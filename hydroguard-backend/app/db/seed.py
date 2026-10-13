"""Seed data mechanism for HydroGuard database.

Provides optional demo data generation clearly marked as simulated.
Can be disabled or removed for production use.
"""

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.hostel_config import (
    CANONICAL_NODE_ID,
    TANKS,
    block_name,
    canonical_node_location,
    canonical_node_name,
)
from app.db.database import get_db_context
from app.db.models import Alert, Node, SensorReading
from app.db.repositories import NodeRepository, SensorReadingRepository


def seed_demo_data(
    db: Session,
    node_id: str = CANONICAL_NODE_ID,
    node_name: str = canonical_node_name(),
    node_location: str = canonical_node_location(),
    days: int = 30,
) -> int:
    """Seed demo water quality data for development.

    Args:
        db: Database session
        node_id: Node identifier
        node_name: Node display name
        node_location: Node location
        days: Number of days of data to generate

    Returns:
        Number of readings created
    """
    NodeRepository.get_or_create(
        db=db,
        node_id=node_id,
        name=node_name,
        location=node_location,
        status="offline",
    )

    backend_root = Path(__file__).resolve().parents[2]
    data_file = backend_root / "data" / "development_water_quality_200_observations.csv"

    readings_created = 0

    if data_file.exists():
        with open(data_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
            for i, row in enumerate(reader):
                if i >= days:
                    break
                timestamp = datetime.now(timezone.utc) - timedelta(days=days - i)
                SensorReadingRepository.create(
                    db=db,
                    node_id=node_id,
                    timestamp=timestamp,
                    ph=float(row["pH"]),
                    tds=float(row["TDS"]),
                    turbidity=float(row["turbidity"]),
                    temperature=float(row["temperature"]),
                    red=int(row.get("rgb_red") or row.get("red")) if row.get("rgb_red") or row.get("red") else None,
                    green=int(row.get("rgb_green") or row.get("green")) if row.get("rgb_green") or row.get("green") else None,
                    blue=int(row.get("rgb_blue") or row.get("blue")) if row.get("rgb_blue") or row.get("blue") else None,
                    clear=int(row.get("rgb_clear") or row.get("clear")) if row.get("rgb_clear") or row.get("clear") else None,
                    optical_colour_index=float(row.get("optical_colour_index", "0.12")),
                    source="SIMULATED_DEVELOPMENT",
                )
                readings_created += 1
    else:
        base_time = datetime.now(timezone.utc) - timedelta(days=days)
        for i in range(days):
            timestamp = base_time + timedelta(days=i)
            ph = 7.0 + (i % 10) * 0.1
            tds = 200.0 + (i % 20) * 10.0
            turbidity = 1.0 + (i % 5) * 0.2
            temperature = 22.0 + (i % 10) * 0.5
            optical_colour_index = 0.12 + ((i * 7) % 23) / 100
            SensorReadingRepository.create(
                db=db,
                node_id=node_id,
                timestamp=timestamp,
                ph=ph,
                tds=tds,
                turbidity=turbidity,
                temperature=temperature,
                optical_colour_index=optical_colour_index,
                source="SIMULATED",
            )
            readings_created += 1

    return readings_created


def seed_multiple_nodes(db: Session) -> dict:
    """Seed demo data for the deployed hostel.

    The deployment has one building, one block and one water tank, so this
    seeds exactly the canonical tank. It used to seed three example tanks
    ("Block A", "Block B", "Mess") that do not exist in the real hostel.
    """
    nodes_config = [
        {
            "node_id": tank["node_id"],
            "node_name": tank["name"],
            "node_location": canonical_node_location(),
            "days": 30,
        }
        for tank in TANKS
    ]
    results = {}
    for config in nodes_config:
        count = seed_demo_data(
            db=db,
            node_id=config["node_id"],
            node_name=config["node_name"],
            node_location=config["node_location"],
            days=config["days"],
        )
        results[config["node_id"]] = count
    return results


def seed_development_dataset(db: Session, node_id: str = "node_overhead_a") -> int:
    """Idempotently seed the canonical 200-observation development dataset.

    Real sensor readings, other nodes, forecasts, model errors, checkpoints, and
    research artifacts are retained. The return value is the number inserted;
    zero means the checked-in development dataset was already present.
    """
    backend_root = Path(__file__).resolve().parents[2]
    data_file = backend_root / "data" / "development_water_quality_200_observations.csv"
    with data_file.open(newline="", encoding="utf-8") as source_file:
        rows = list(csv.DictReader(line for line in source_file if not line.lstrip().startswith("#")))
    if len(rows) != 200:
        raise ValueError("The development dataset must contain exactly 200 simulated observations.")

    def field(row, *names):
        for name in names:
            if row.get(name) not in (None, ""):
                return row[name]
        raise ValueError(f"Development observation is missing {names[0]}.")

    # The deployed tank always carries the canonical deployment labels, even if
    # an earlier ingestion run auto-created the row with placeholder text.
    canonical = node_id == CANONICAL_NODE_ID
    node_name = canonical_node_name() if canonical else "Overhead Tank A"
    node_location = canonical_node_location() if canonical else "Hostel Block A"
    node = NodeRepository.get_or_create(
        db=db,
        node_id=node_id,
        name=node_name,
        location=node_location,
        status="offline",
    )
    placeholder_names = {"", "unknown", node_id.lower(), f"node {node_id}".lower()}
    if canonical:
        _ensure_labels(db, node, node_name, node_location)
    else:
        # Earlier ingestion runs auto-create nodes with placeholder labels;
        # repair them so the demo node presents a real name and location.
        if (node.name or "").strip().lower() in placeholder_names:
            node.name = node_name
        if (node.location or "").strip().lower() in {"", "unknown", "test"}:
            node.location = node_location
        db.commit()

    # Idempotency check: if 200+ SIMULATED_DEVELOPMENT readings already exist, skip
    existing_count = db.query(SensorReading).filter(
        SensorReading.node_id == node_id,
        SensorReading.source == "SIMULATED_DEVELOPMENT",
    ).count()
    if existing_count >= 200:
        return 0  # Dataset already seeded

    legacy_development_sources = (
        "DEMO", "SIMULATED", "HISTORICAL_DEMO", "HISTORICAL_OR_SIMULATED",
        "SIMULATED_DEVELOPMENT",
    )
    real_readings_exist = db.query(SensorReading).filter(
        SensorReading.node_id == node_id,
        func.upper(SensorReading.source).in_(("REAL_SENSOR", "THINGSPEAK", "ESP32")),
    ).first() is not None
    if real_readings_exist:
        db.query(SensorReading).filter(
            SensorReading.node_id == node_id,
            func.upper(SensorReading.source).in_(legacy_development_sources),
        ).delete(synchronize_session=False)
    else:
        db.query(SensorReading).filter(
            SensorReading.node_id == node_id,
            func.upper(SensorReading.source).in_(legacy_development_sources),
        ).delete(synchronize_session=False)

    db.query(Alert).filter(Alert.node_id == node_id).delete(synchronize_session=False)
    db.expunge_all()

    inserted = []
    seed_anchor = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    expected = list(rows)
    for index, row in enumerate(expected):
        timestamp = seed_anchor - timedelta(days=len(expected) - index - 1)
        inserted.append(SensorReading(
            node_id=node_id,
            timestamp=timestamp.replace(tzinfo=timezone.utc),
            ph=float(field(row, "pH", "ph")),
            tds=float(field(row, "TDS", "tds")),
            turbidity=float(field(row, "turbidity")),
            temperature=float(field(row, "temperature")),
            red=int(field(row, "rgb_red", "red")),
            green=int(field(row, "rgb_green", "green")),
            blue=int(field(row, "rgb_blue", "blue")),
            clear=int(field(row, "rgb_clear", "clear")),
            optical_colour_index=float(field(row, "optical_colour_index")),
            source="SIMULATED_DEVELOPMENT",
        ))
    db.add_all(inserted)
    db.commit()

    from app.services.alert_service import AlertService
    for reading in inserted:
        AlertService.evaluate_reading_for_alerts(db, node_id, {
            "timestamp": reading.timestamp,
            "ph": float(reading.ph),
            "tds": float(reading.tds),
            "turbidity": float(reading.turbidity),
            "temperature": float(reading.temperature),
        })
    return len(inserted)


def _ensure_labels(db: Session, node: Node, name: str, location: str) -> Node:
    """Keep a configured node's display labels in sync with the deployment.

    ``get_or_create`` intentionally leaves an existing row alone, so an
    earlier auto-created row could keep a placeholder or an example label
    such as "Overhead Tank B". Seeding is the point where the configured
    labels are authoritative.
    """
    changed = False
    if (node.name or "").strip() != name:
        node.name = name
        changed = True
    if (node.location or "").strip() != location:
        node.location = location
        changed = True
    if changed:
        db.commit()
    return node


def seed_devices(db: Session) -> dict:
    """Seed the deployed tank with NO readings (status only).

    Only the canonical hostel tank is created; the old Block B and Mess
    example nodes are not part of the deployment.
    """
    results = {}
    for tank in TANKS:
        location = block_name(tank["block_id"])
        node = NodeRepository.get_or_create(
            db=db,
            node_id=tank["node_id"],
            name=tank["name"],
            location=location,
            status="offline",
        )
        _ensure_labels(db, node, tank["name"], location)
        results[tank["node_id"]] = "node reset"
    return results


def main():
    """Seed the canonical 200-observation development data on the primary demo node."""
    print("Seeding HydroGuard 200-observation development data...")
    print("=" * 70)

    with get_db_context() as db:
        count = seed_development_dataset(db)
        seed_devices(db)

        print(f"\nSeeding complete: {count} readings created.")
        print("\n" + "=" * 70)
        print("IMPORTANT:")
        print("- All seeded data is marked as SIMULATED_DEVELOPMENT")
        print("- This is NOT real sensor data")
        print("- Development data is seeded automatically only in explicit dev mode")
        print("=" * 70)


if __name__ == "__main__":
    main()