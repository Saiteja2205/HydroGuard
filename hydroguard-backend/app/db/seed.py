"""Seed data mechanism for HydroGuard database.

Provides optional demo data generation clearly marked as simulated.
Can be disabled or removed for production use.
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.database import get_db_context
from app.db.models import Node, SensorReading
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
    data_file = backend_root / "data" / "demo_water_quality_200days.csv"

    readings_created = 0

    if data_file.exists():
        # Load from CSV file
        with open(data_file) as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= days:
                    break

                # Generate timestamp (going back from now)
                timestamp = datetime.now(timezone.utc) - timedelta(days=days - i)

                SensorReadingRepository.create(
                    db=db,
                    node_id=node_id,
                    timestamp=timestamp,
                    ph=float(row["pH"]),
                    tds=float(row["TDS"]),
                    turbidity=float(row["turbidity"]),
                    temperature=float(row["temperature"]),
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

            SensorReadingRepository.create(
                db=db,
                node_id=node_id,
                timestamp=timestamp,
                ph=ph,
                tds=tds,
                turbidity=turbidity,
                temperature=temperature,
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


def main():
    """Main entry point for seeding demo data."""
    print("Seeding HydroGuard demo data...")
    print("=" * 70)

    with get_db_context() as db:
        # Seed multiple nodes
        results = seed_multiple_nodes(db)

        print("\nSeeding complete:")
        for node_id, count in results.items():
            print(f"  {node_id}: {count} readings")

        print("\n" + "=" * 70)
        print("IMPORTANT:")
        print("- All seeded data is marked as 'historical_demo' or 'simulated'")
        print("- This is NOT real sensor data")
        print("- Remove this data before production deployment")
        print("=" * 70)


if __name__ == "__main__":
    main()
