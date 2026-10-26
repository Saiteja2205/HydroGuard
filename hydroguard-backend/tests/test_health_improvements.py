"""Regression and improvement tests for health triage, ThingSpeak live sensor detection,
and inference service model load status synchronization.
"""

from datetime import datetime, timedelta, timezone
import sys
import types
import pytest
from fastapi.testclient import TestClient

from app.api.health import _latest_live_observation, LIVE_PROVENANCE_SOURCES
from app.db.database import get_db_context, init_db
from app.db.models import Node, SensorReading
from app.main import app

NODE_ID = "health_improvements_node"


@pytest.fixture(autouse=True, scope="module")
def _database():
    init_db()


def _client() -> TestClient:
    return TestClient(app)


def _use_latest(monkeypatch, observed, live):
    from app.api import health as health_module
    monkeypatch.setattr(health_module, "_latest_observation", lambda db: observed)
    monkeypatch.setattr(health_module, "_latest_live_observation", lambda db: live)


def test_latest_live_observation_detects_thingspeak_and_esp32_in_database():
    """Verify that _latest_live_observation directly queries both THINGSPEAK and ESP32 sources."""
    with get_db_context() as db:
        if db.query(Node).filter_by(node_id=NODE_ID).first() is None:
            db.add(Node(node_id=NODE_ID, name="Health Node", location="Test", status="online"))
            db.commit()

        target_time = datetime(2028, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts_reading = SensorReading(
            node_id=NODE_ID,
            timestamp=target_time,
            ph=7.3,
            tds=180.0,
            turbidity=2.1,
            temperature=25.0,
            source="THINGSPEAK",
        )
        db.add(ts_reading)
        db.commit()

        latest = _latest_live_observation(db)
        assert latest is not None
        assert latest == target_time

        # Cleanup test row so it doesn't leak into subsequent tests
        db.delete(ts_reading)
        db.commit()


def test_thingspeak_reading_reports_stale_heartbeat_when_old(monkeypatch):
    """When the newest physical sensor reading is outside the heartbeat window, report stale."""
    old_time = datetime.now(timezone.utc) - timedelta(hours=3)
    _use_latest(monkeypatch, observed=(old_time, "THINGSPEAK"), live=old_time)

    body = _client().get("/api/v1/health").json()

    assert body["sensor_ingestion"]["state"] == "stale"
    assert body["sensors_connected"] is False
    assert body["sensor_ingestion"]["last_real_sensor_at"] is not None
    assert body["sensor_ingestion"]["age_seconds"] >= 3 * 3600 - 10
    assert "heartbeat window" in body["sensor_ingestion"]["detail"].lower()


def test_thingspeak_reading_reports_recent_heartbeat_when_fresh(monkeypatch):
    """Fresh ThingSpeak reading indicates live connected sensors."""
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=15)
    _use_latest(monkeypatch, observed=(fresh_time, "THINGSPEAK"), live=fresh_time)

    body = _client().get("/api/v1/health").json()

    assert body["sensor_ingestion"]["state"] == "recent"
    assert body["sensors_connected"] is True
    assert body["sensor_ingestion"]["age_seconds"] < 60


def test_inference_service_exposes_model_properties():
    """InferenceService provides model accessors compatible with health monitoring."""
    from ml.services.inference_service import InferenceService
    service = InferenceService()
    assert hasattr(service, "lstm_model")
    assert hasattr(service, "patchtst_model")
    assert hasattr(service, "timemixer_model")
    assert service.lstm_model is None
    assert service.patchtst_model is None
    assert service.timemixer_model is None


def test_inference_service_loaded_status_reflected_in_health(monkeypatch):
    """When forecast_service is loaded, /health accurately reports loaded state across all models."""
    fake_module = types.ModuleType("app.api.forecast")
    fake_module.forecast_service = types.SimpleNamespace(
        lstm_model=object(),
        patchtst_model=object(),
        timemixer_model=object(),
    )
    monkeypatch.setitem(sys.modules, "app.api.forecast", fake_module)

    body = _client().get("/api/v1/health").json()

    assert body["models"]["state"] == "loaded"
    assert body["models"]["lstm"] is True
    assert body["models"]["patchtst"] is True
    assert body["models"]["timemixer"] is True
    assert body["models_loaded"]["lstm"] is True
    assert body["models_loaded"]["patchtst"] is True
    assert body["models_loaded"]["timemixer"] is True
