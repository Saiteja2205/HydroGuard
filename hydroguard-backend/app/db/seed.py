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

from app.db.database import get_db_context
from app.db.models import Alert, Node, SensorReading
from app.db.repositories import NodeRepository, SensorReadingRepository


def seed_demo_data(
    db: Session,
    node_id: str = "node_overhead_a",
    node_name: str = "Overhead Tank A",
    node_location: str = "Hostel Block A",
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
    # Create node
    NodeRepository.get_or_create(
        db=db,
        node_id=node_id,
        name=node_name,
        location=node_location,
        status="offline",
    )

    # Check if data file exists
    backend_root = Path(__file__).resolve().parents[2]
    # Prefer the checked-in five-parameter development fixture. The older
    # 200-day CSV contains only pH/TDS/turbidity/temperature plus legacy EC/DO.
    data_file = backend_root / "data" / "development_water_quality_200_observations.csv"
    if not data_file.exists():
        data_file = backend_root / "data" / "demo_water_quality_200days.csv"

    readings_created = 0

    if data_file.exists():
        # Load from the canonical fixture, ignoring its provenance comments.
        with open(data_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
            for i, row in enumerate(reader):
                if i >= days:
                    break

                # Generate timestamp (going back from now)
                timestamp = datetime.now(timezone.utc) - timedelta(days=days - i)

                optical_colour_index = row.get("optical_colour_index")
                if optical_colour_index in (None, ""):
                    # Synthetic legacy fallback only; the primary fixture has
                    # explicit, varying optical-index values.
                    optical_colour_index = 0.12 + ((i * 7) % 23) / 100

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
                    optical_colour_index=float(optical_colour_index),
                    source="DEMO",  # Synthetic dataset; never represented as field data.
                )
                readings_created += 1
    else:
        # Generate synthetic data if CSV not available
        base_time = datetime.now(timezone.utc) - timedelta(days=days)

        for i in range(days):
            timestamp = base_time + timedelta(days=i)

            # Generate values with some variation
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
    """Seed demo data for multiple nodes.

    Args:
        db: Database session

    Returns:
        Dictionary with node_id as key and count of readings as value
    """
    nodes_config = [
        {
            "node_id": "node_overhead_a",
            "node_name": "Overhead Tank A",
            "node_location": "Hostel Block A",
            "days": 30,
        },
        {
            "node_id": "node_overhead_b",
            "node_name": "Overhead Tank B",
            "node_location": "Hostel Block B",
            "days": 30,
        },
        {
            "node_id": "node_mess_ground",
            "node_name": "Mess Ground Water",
            "node_location": "Mess Area",
            "days": 30,
        },
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

    def field(row: dict[str, str], *names: str) -> str:
        for name in names:
            if row.get(name) not in (None, ""):
                return row[name]
        raise ValueError(f"Development observation is missing {names[0]}.")

    NodeRepository.get_or_create(
        db=db,
        node_id=node_id,
        name="Overhead Tank A",
        location="Hostel Block A",
        status="offline",
    )

    # Keep the checked-in values and order stable while rolling their database
    # timestamps forward. The model fixture remains reproducible; the API's
    # development history always has a usable recent window.
    seed_anchor = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    expected = list(rows)
    existing = (
        db.query(SensorReading)
        .filter_by(node_id=node_id, source="SIMULATED_DEVELOPMENT")
        .order_by(SensorReading.timestamp.asc())
        .all()
    )

    def matches_dataset() -> bool:
        if len(existing) != len(expected):
            return False
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=30)
        recent_timestamps: set[datetime] = set()
        for reading in existing:
            timestamp = reading.timestamp
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
            if recent_cutoff <= timestamp <= now and all(
                value is not None and math.isfinite(float(value))
                for value in (
                    reading.ph,
                    reading.tds,
                    reading.turbidity,
                    reading.temperature,
                    reading.optical_colour_index,
                )
            ):
                recent_timestamps.add(timestamp)
        if len(recent_timestamps) < 30:
            return False

        for reading, row in zip(existing, expected):
            values = (
                (("pH", "ph"), reading.ph), (("TDS", "tds"), reading.tds),
                (("turbidity",), reading.turbidity), (("temperature",), reading.temperature),
                (("optical_colour_index",), reading.optical_colour_index),
            )
            if any(
                actual is None or not math.isclose(float(actual), float(field(row, *keys)), abs_tol=0.0001)
                for keys, actual in values
            ):
                return False
            raw_fields = (("rgb_red", "red"), ("rgb_green", "green"), ("rgb_blue", "blue"), ("rgb_clear", "clear"))
            if any(getattr(reading, name) != int(field(row, *keys)) for (keys, name) in zip(raw_fields, ("red", "green", "blue", "clear"))):
                return False
        return True

    if matches_dataset():
        return 0

    legacy_development_sources = (
        "DEMO", "SIMULATED", "HISTORICAL_DEMO", "HISTORICAL_OR_SIMULATED",
        "SIMULATED_DEVELOPMENT",
    )
    db.query(SensorReading).filter(
        SensorReading.node_id == node_id,
        func.upper(SensorReading.source).in_(legacy_development_sources),
    ).delete(synchronize_session=False)

    # Existing primary-node alerts in this local database were generated by
    # its demo readings. Retain them if any real sensor rows have arrived.
    has_real_readings = db.query(SensorReading.id).filter(
        SensorReading.node_id == node_id,
        func.upper(SensorReading.source).in_(("REAL_SENSOR", "THINGSPEAK", "ESP32")),
    ).first() is not None
    if not has_real_readings:
        db.query(Alert).filter(Alert.node_id == node_id).delete(synchronize_session=False)

    # Clear detached rows loaded above before SQLite can reuse their primary keys.
    db.expunge_all()

    inserted = []
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


def main():
    """Seed the canonical 200-observation review dataset on the primary demo node."""
    print("Seeding HydroGuard 200-observation development data...")
    print("=" * 70)

    with get_db_context() as db:
        count = seed_development_dataset(db)

        print(f"\nSeeding complete: {count} readings created.")
        print("\n" + "=" * 70)
        print("IMPORTANT:")
        print("- All seeded data is marked as SIMULATED_DEVELOPMENT")
        print("- This is NOT real sensor data")
        print("- Development data is seeded automatically only in explicit dev mode")
        print("=" * 70)


if __name__ == "__main__":
    main()
