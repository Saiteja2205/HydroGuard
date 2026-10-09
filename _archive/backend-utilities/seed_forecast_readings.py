from datetime import datetime, timedelta, timezone
from app.db.database import get_db_context
from app.db.repositories import NodeRepository, SensorReadingRepository

with get_db_context() as db:
    # Ensure node exists
    NodeRepository.get_or_create(
        db=db,
        node_id="node_overhead_a",
        name="Overhead Tank A",
        location="Hostel Block A",
    )

    # Seed 30 historical readings
    base_time = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(30):
        timestamp = base_time + timedelta(days=i)
        SensorReadingRepository.create(
            db=db,
            node_id="node_overhead_a",
            timestamp=timestamp,
            ph=7.0 + (i % 10) * 0.1,
            tds=180.0 + (i % 20) * 5.0,
            turbidity=1.0 + (i % 5) * 0.2,
            temperature=22.0 + (i % 10) * 0.5,
            ec=None,
            do=None,
            flow_rate=18.0,
            source="simulated",
        )

print("Seeded 30 historical readings for forecast testing")
