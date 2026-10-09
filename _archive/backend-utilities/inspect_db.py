from app.db.database import get_db_context
from app.db.models import Node, SensorReading, Forecast, ModelError, Alert
from sqlalchemy import text
from sqlalchemy import text

with get_db_context() as db:
    # Check table counts
    node_count = db.query(Node).count()
    reading_count = db.query(SensorReading).count()
    forecast_count = db.query(Forecast).count()
    error_count = db.query(ModelError).count()
    alert_count = db.query(Alert).count()

    print("Database Record Counts:")
    print(f"  Nodes: {node_count}")
    print(f"  Sensor Readings: {reading_count}")
    print(f"  Forecasts: {forecast_count}")
    print(f"  Model Errors: {error_count}")
    print(f"  Alerts: {alert_count}")

    # Check indexes
    print("\nChecking indexes...")
    result = db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sensor_readings'"))
    indexes = result.fetchall()
    print(f"  sensor_readings indexes: {[row[0] for row in indexes]}")

    result = db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='forecasts'"))
    indexes = result.fetchall()
    print(f"  forecasts indexes: {[row[0] for row in indexes]}")

    result = db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='model_errors'"))
    indexes = result.fetchall()
    print(f"  model_errors indexes: {[row[0] for row in indexes]}")

    result = db.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='alerts'"))
    indexes = result.fetchall()
    print(f"  alerts indexes: {[row[0] for row in indexes]}")

print("\nDatabase inspection complete")
