from app.db.database import get_db_context
from app.db.models import SensorReading
from sqlalchemy import select

with get_db_context() as db:
    reading = db.execute(
        select(SensorReading)
        .where(SensorReading.node_id == 'node_overhead_a')
        .order_by(SensorReading.timestamp.desc())
        .limit(1)
    ).scalar_one_or_none()
    print(f'Reading ID: {reading.id}')
    print(f'pH: {reading.ph}')
    print(f'EC: {reading.ec}')
    print(f'DO: {reading.do}')
    print(f'source: {reading.source}')
