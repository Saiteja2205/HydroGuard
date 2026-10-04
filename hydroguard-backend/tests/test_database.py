"""Database tests for HydroGuard.

Tests database initialization, model creation, and repository operations.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import database functions first
from app.db.database import get_db_context, init_db, reset_db

# Initialize database first (this imports models internally)
init_db()

# Now import models and repositories after init_db
from app.db.models import Node, SensorReading, Forecast, ModelError, Alert
from app.db.repositories import (
    NodeRepository,
    SensorReadingRepository,
    ForecastRepository,
    ModelErrorRepository,
    AlertRepository,
)


def test_database_initialization():
    """Test that database tables are created correctly."""
    print("\n" + "=" * 70)
    print("TEST: Database Initialization")
    print("=" * 70)

    with get_db_context() as db:
        # Check that tables exist by querying them
        nodes = db.query(Node).all()
        print(f"[OK] Nodes table accessible, count: {len(nodes)}")

        readings = db.query(SensorReading).all()
        print(f"[OK] SensorReadings table accessible, count: {len(readings)}")

        forecasts = db.query(Forecast).all()
        print(f"[OK] Forecasts table accessible, count: {len(forecasts)}")

        errors = db.query(ModelError).all()
        print(f"[OK] ModelErrors table accessible, count: {len(errors)}")

        alerts = db.query(Alert).all()
        print(f"[OK] Alerts table accessible, count: {len(alerts)}")

    from app.db.database import engine
    forecast_columns = {column["name"] for column in inspect(engine).get_columns("forecasts")}
    expected_forecast_columns = {
        "lstm_ph", "lstm_tds", "lstm_turbidity", "lstm_temperature",
        "patchtst_ph", "patchtst_tds", "patchtst_turbidity", "patchtst_temperature",
        "timemixer_ph", "timemixer_tds", "timemixer_turbidity", "timemixer_temperature",
        "ensemble_ph", "ensemble_tds", "ensemble_turbidity", "ensemble_temperature",
        "lstm_optical_colour_index", "patchtst_optical_colour_index",
        "timemixer_optical_colour_index", "ensemble_optical_colour_index",
        "lstm_weight_optical_colour_index", "patchtst_weight_optical_colour_index",
        "timemixer_weight_optical_colour_index",
        "lstm_weight_ph", "patchtst_weight_ph", "timemixer_weight_ph",
        "lstm_weight_tds", "patchtst_weight_tds", "timemixer_weight_tds",
        "lstm_weight_turbidity", "patchtst_weight_turbidity", "timemixer_weight_turbidity",
        "lstm_weight_temperature", "patchtst_weight_temperature", "timemixer_weight_temperature",
    }
    assert expected_forecast_columns <= forecast_columns

    print("\n[OK] Database initialization test passed")


def test_node_repository():
    """Test node repository operations."""
    print("\n" + "=" * 70)
    print("TEST: Node Repository")
    print("=" * 70)

    with get_db_context() as db:
        # Clean up any existing test data
        db.query(Node).filter(Node.node_id == "test_node_1").delete()
        db.commit()

        # Create node
        node = NodeRepository.create(
            db=db,
            node_id="test_node_1",
            name="Test Node 1",
            location="Test Location",
            status="offline",
        )
        print(f"[OK] Created node: {node.node_id}")

        # Get node
        retrieved = NodeRepository.get_by_node_id(db, "test_node_1")
        assert retrieved is not None
        assert retrieved.node_id == "test_node_1"
        print(f"[OK] Retrieved node: {retrieved.node_id}")

        # Get or create (should retrieve existing)
        node2 = NodeRepository.get_or_create(
            db=db,
            node_id="test_node_1",
            name="Test Node 1",
            location="Test Location",
        )
        assert node2.id == node.id
        print(f"[OK] Get or create returned existing node")

        # Update status
        updated = NodeRepository.update_status(db, "test_node_1", "online")
        assert updated.status == "online"
        print(f"[OK] Updated node status to: {updated.status}")

        # List all
        all_nodes = NodeRepository.list_all(db)
        assert len(all_nodes) >= 1
        print(f"[OK] Listed nodes: {len(all_nodes)}")

    print("\n[OK] Node repository test passed")


def test_sensor_reading_repository():
    """Test sensor reading repository operations."""
    print("\n" + "=" * 70)
    print("TEST: Sensor Reading Repository")
    print("=" * 70)

    with get_db_context() as db:
        # Clean up any existing test data
        db.query(SensorReading).filter(SensorReading.node_id == "test_node_2").delete()
        db.commit()

        # Create node first (using get_or_create to avoid duplicates)
        NodeRepository.get_or_create(
            db=db,
            node_id="test_node_2",
            name="Test Node 2",
            location="Test Location",
        )

        # Create reading
        reading = SensorReadingRepository.create(
            db=db,
            node_id="test_node_2",
            timestamp=datetime.now(timezone.utc),
            ph=7.2,
            tds=180.0,
            turbidity=1.2,
            temperature=22.4,
            red=1200,
            green=1300,
            blue=1400,
            clear=3900,
            optical_colour_index=None,
            source="HISTORICAL_DATA",
        )
        print(f"[OK] Created reading: id={reading.id}, ph={reading.ph}")

        # Get latest
        latest = SensorReadingRepository.get_latest_by_node(db, "test_node_2")
        assert latest is not None
        print(f"[DEBUG] Latest reading: id={latest.id}, ph={latest.ph}, node_id={latest.node_id}, type={type(latest.ph)}")
        assert abs(float(latest.ph) - 7.2) < 0.01  # Allow for floating point precision
        print(f"[OK] Retrieved latest reading: ph={latest.ph}")

        # Get history
        history = SensorReadingRepository.get_history_by_node(db, "test_node_2", limit=10)
        assert len(history) == 1
        print(f"[OK] Retrieved history: {len(history)} readings")

        # Get count
        count = SensorReadingRepository.get_count_by_node(db, "test_node_2")
        assert count == 1
        print(f"[OK] Counted readings: {count}")

    print("\n[OK] Sensor reading repository test passed")


def test_forecast_repository():
    """Test forecast repository operations."""
    print("\n" + "=" * 70)
    print("TEST: Forecast Repository")
    print("=" * 70)

    with get_db_context() as db:
        # Clean up any existing test data
        db.query(Forecast).filter(Forecast.node_id == "test_node_3").delete()
        db.commit()

        # Create node using get_or_create
        NodeRepository.get_or_create(
            db=db,
            node_id="test_node_3",
            name="Test Node 3",
            location="Test Location",
        )

        # Create forecast
        forecast_date = datetime.now(timezone.utc)
        forecast = ForecastRepository.create(
            db=db,
            node_id="test_node_3",
            forecast_date=forecast_date,
            lstm_predictions={"pH": 7.0, "TDS": 180.0, "turbidity": 1.2, "temperature": 22.0, "optical_colour_index": 0.51},
            patchtst_predictions={"pH": 7.1, "TDS": 182.0, "turbidity": 1.3, "temperature": 22.2, "optical_colour_index": 0.52},
            timemixer_predictions={"pH": 7.05, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.53},
            ensemble_predictions={"pH": 7.05, "TDS": 181.0, "turbidity": 1.25, "temperature": 22.1, "optical_colour_index": 0.52},
            weights={
                "pH": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
                "TDS": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
                "turbidity": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
                "temperature": {"LSTM": 0.33, "PatchTST": 0.33, "TimeMixer": 0.34},
                "optical_colour_index": {"LSTM": 0.25, "PatchTST": 0.35, "TimeMixer": 0.40},
            },
        )
        print(f"[OK] Created forecast: id={forecast.id}")
        assert float(forecast.lstm_optical_colour_index) == 0.51
        assert float(forecast.patchtst_optical_colour_index) == 0.52
        assert float(forecast.timemixer_optical_colour_index) == 0.53
        assert float(forecast.ensemble_optical_colour_index) == 0.52
        assert float(forecast.lstm_weight_optical_colour_index) == 0.25

        # Get forecasts
        forecasts = ForecastRepository.get_by_node(db, "test_node_3", limit=10)
        assert len(forecasts) == 1
        print(f"[OK] Retrieved forecasts: {len(forecasts)}")

        # Get by date
        by_date = ForecastRepository.get_by_date(db, "test_node_3", forecast_date)
        assert by_date is not None
        print(f"[OK] Retrieved forecast by date")

        # Get latest
        latest = ForecastRepository.get_latest_by_node(db, "test_node_3")
        assert latest is not None
        print(f"[OK] Retrieved latest forecast")

    print("\n[OK] Forecast repository test passed")


def test_model_error_repository():
    """Test model error repository operations."""
    print("\n" + "=" * 70)
    print("TEST: Model Error Repository")
    print("=" * 70)

    with get_db_context() as db:
        # Clean up any existing test data
        db.query(ModelError).filter(ModelError.node_id == "test_node_4").delete()
        db.commit()

        # Create node using get_or_create
        NodeRepository.get_or_create(
            db=db,
            node_id="test_node_4",
            name="Test Node 4",
            location="Test Location",
        )

        # Create error
        forecast_date = datetime.now(timezone.utc)
        error = ModelErrorRepository.create(
            db=db,
            node_id="test_node_4",
            forecast_id=None,
            forecast_date=forecast_date,
            model_name="LSTM",
            parameter="pH",
            predicted_value=7.0,
            actual_value=7.1,
            absolute_error=0.1,
            squared_error=0.01,
            mae=0.1,
            rmse=0.1,
        )
        print(f"[OK] Created model error: id={error.id}")

        # Get errors
        errors = ModelErrorRepository.get_by_node(db, "test_node_4", limit=10)
        assert len(errors) == 1
        print(f"[OK] Retrieved errors: {len(errors)}")

        # Get average errors
        avg_errors = ModelErrorRepository.get_average_errors(db, "test_node_4")
        assert "LSTM" in avg_errors
        print(f"[OK] Retrieved average errors: {len(avg_errors)} models")

    print("\n[OK] Model error repository test passed")


def test_alert_repository():
    """Test alert repository operations."""
    print("\n" + "=" * 70)
    print("TEST: Alert Repository")
    print("=" * 70)

    with get_db_context() as db:
        # Clean up any existing test data
        db.query(Alert).filter(Alert.node_id == "test_node_5").delete()
        db.commit()

        # Create node using get_or_create
        NodeRepository.get_or_create(
            db=db,
            node_id="test_node_5",
            name="Test Node 5",
            location="Test Location",
        )

        # Create alert
        alert = AlertRepository.create(
            db=db,
            node_id="test_node_5",
            timestamp=datetime.now(timezone.utc),
            parameter="pH",
            value=6.0,
            threshold=6.5,
            severity="WARNING",
            message="pH below minimum threshold",
            status="ACTIVE",
        )
        print(f"[OK] Created alert: id={alert.id}")

        # Get alerts
        alerts = AlertRepository.get_by_node(db, "test_node_5", limit=10)
        assert len(alerts) == 1
        print(f"[OK] Retrieved alerts: {len(alerts)}")

        # Get active alerts
        active = AlertRepository.get_active_by_node(db, "test_node_5")
        assert len(active) == 1
        print(f"[OK] Retrieved active alerts: {len(active)}")

        # Update status
        updated = AlertRepository.update_status(db, alert.id, "ACKNOWLEDGED")
        assert updated.status == "ACKNOWLEDGED"
        print(f"[OK] Updated alert status to: {updated.status}")

    print("\n[OK] Alert repository test passed")


def run_all_database_tests():
    """Run all database tests."""
    print("\n" + "=" * 70)
    print("RUNNING ALL DATABASE TESTS")
    print("=" * 70)

    test_database_initialization()
    test_node_repository()
    test_sensor_reading_repository()
    test_forecast_repository()
    test_model_error_repository()
    test_alert_repository()

    print("\n" + "=" * 70)
    print("ALL DATABASE TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    run_all_database_tests()
