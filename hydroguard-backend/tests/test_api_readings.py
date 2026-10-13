"""API tests for readings endpoints."""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db, get_db_context
from app.db.repositories import NodeRepository, SensorReadingRepository


def test_readings_api(monkeypatch, authenticated_client):
    """Test readings API endpoints."""
    print("\n" + "=" * 70)
    print("TEST: Readings API")
    print("=" * 70)

    # Initialize database
    init_db()

    client = authenticated_client
    monkeypatch.delenv("HYDROGUARD_SENSOR_API_KEY", raising=False)

    # Create test node (use get_or_create to avoid conflicts)
    with get_db_context() as db:
        NodeRepository.get_or_create(
            db=db,
            node_id="test_api_node_1",
            name="Test API Node 1",
            location="Test Location",
        )

    # Test POST /readings
    print("\n1. Testing POST /readings:")
    reading_data = {
        "node_id": "test_api_node_1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ph": 7.2,
        "tds": 180.0,
        "turbidity": 1.2,
        "temperature": 22.4,
        "red": 1200,
        "green": 1300,
        "blue": 1400,
        "clear": 3900,
        "source": "DEMO",
    }
    unconfigured = client.post("/api/v1/readings", json=reading_data)
    assert unconfigured.status_code == 503
    monkeypatch.setenv("HYDROGUARD_SENSOR_API_KEY", "test-sensor-key")
    sensor_headers = {"X-Sensor-Token": "test-sensor-key"}
    response = client.post("/api/v1/readings", json=reading_data, headers=sensor_headers)
    assert response.status_code == 200
    result = response.json()
    assert result["node_id"] == "test_api_node_1"
    assert result["ph"] == 7.2
    print(f"   [OK] POST /readings succeeded")

    # Test GET latest reading
    print("\n2. Testing GET /nodes/{node_id}/readings/latest:")
    response = client.get("/api/v1/nodes/test_api_node_1/readings/latest")
    assert response.status_code == 200
    result = response.json()
    assert result["node_id"] == "test_api_node_1"
    assert result["ph"] == 7.2
    print(f"   [OK] GET latest reading succeeded")

    # Test GET history
    print("\n3. Testing GET /nodes/{node_id}/readings/history:")
    response = client.get("/api/v1/nodes/test_api_node_1/readings/history?limit=10")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] >= 1
    print(f"   [OK] GET history succeeded: {result['count']} readings")

    # Test validation - negative TDS
    print("\n4. Testing validation (negative TDS):")
    invalid_data = reading_data.copy()
    invalid_data["tds"] = -10.0
    response = client.post("/api/v1/readings", json=invalid_data, headers=sensor_headers)
    assert response.status_code == 422  # Validation error
    print(f"   [OK] Validation rejected negative TDS")

    # Test validation - negative turbidity
    print("\n5. Testing validation (negative turbidity):")
    invalid_data = reading_data.copy()
    invalid_data["turbidity"] = -1.0
    response = client.post("/api/v1/readings", json=invalid_data, headers=sensor_headers)
    assert response.status_code == 422  # Validation error
    print(f"   [OK] Validation rejected negative turbidity")

    # Product contract rejects legacy fields.
    print("\n6. Testing legacy parameter rejection:")
    valid_data = reading_data.copy()
    valid_data["flow_rate"] = 18.0
    response = client.post("/api/v1/readings", json=valid_data, headers=sensor_headers)
    assert response.status_code == 422
    print("   [OK] Legacy flow field rejected")

    clean_response = client.get("/api/v1/nodes/test_api_node_1/readings/latest")
    clean_reading = clean_response.json()
    assert "ec" not in clean_reading and "do" not in clean_reading and "flow_rate" not in clean_reading
    assert clean_reading["red"] == 1200 and clean_reading["clear"] == 3900

    no_reading_node = "test_api_node_no_reading"
    with get_db_context() as db:
        NodeRepository.get_or_create(db, no_reading_node, "No Reading Node", "Test Location")
    empty = client.get(f"/api/v1/nodes/{no_reading_node}/readings/latest")
    assert empty.status_code == 404
    assert "No sensor reading" in empty.json()["detail"]

    print("\n[OK] Readings API test passed")


def test_real_reading_becomes_current_without_replacing_development_history(monkeypatch, authenticated_client):
    init_db()
    monkeypatch.setenv("HYDROGUARD_SENSOR_API_KEY", "test-sensor-key")
    client = authenticated_client
    node_id = "test_live_overrides_development"
    now = datetime.now(timezone.utc)

    development_reading = {
        "node_id": node_id,
        "timestamp": (now + timedelta(minutes=5)).isoformat(),
        "ph": 7.0,
        "tds": 180.0,
        "turbidity": 1.0,
        "temperature": 22.0,
        "red": 10_000,
        "green": 10_200,
        "blue": 10_100,
        "clear": 11_000,
        "optical_colour_index": 0.08,
        "source": "SIMULATED_DEVELOPMENT",
    }
    response = client.post(
        "/api/v1/readings",
        json=development_reading,
        headers={"X-Sensor-Token": "test-sensor-key"},
    )
    assert response.status_code == 200, response.text

    live_reading = {
        **development_reading,
        "timestamp": now.isoformat(),
        "ph": 7.4,
        "tds": 215.0,
        "turbidity": 1.6,
        "temperature": 24.0,
        "red": 9_600,
        "green": 10_000,
        "blue": 10_200,
        "clear": 11_000,
        "optical_colour_index": 0.1,
        "source": "REAL_SENSOR",
    }
    response = client.post(
        "/api/v1/readings",
        json=live_reading,
        headers={"X-Sensor-Token": "test-sensor-key"},
    )
    assert response.status_code == 200, response.text

    latest = client.get(f"/api/v1/nodes/{node_id}/readings/latest")
    assert latest.status_code == 200
    assert latest.json()["source"] == "REAL_SENSOR"
    assert latest.json()["ph"] == 7.4
    assert latest.json()["optical_colour_index"] == 0.1

    history = client.get(f"/api/v1/nodes/{node_id}/readings/history")
    assert history.status_code == 200
    assert history.json()["count"] == 2
    assert {row["source"] for row in history.json()["readings"]} == {
        "REAL_SENSOR",
        "SIMULATED_DEVELOPMENT",
    }


def test_development_reading_apis_serve_the_canonical_simulated_dataset(monkeypatch, authenticated_client):
    from app.db.seed import seed_development_dataset

    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    init_db()
    node_id = "test_200_observation_demo"
    with get_db_context() as db:
        seed_development_dataset(db, node_id=node_id)

    client = authenticated_client
    latest = client.get(f"/api/v1/nodes/{node_id}/readings/latest")
    history = client.get(f"/api/v1/nodes/{node_id}/readings/history?limit=1000")

    assert latest.status_code == 200, latest.text
    assert history.status_code == 200, history.text
    assert latest.json()["source"] == "SIMULATED_DEVELOPMENT"
    assert history.json()["count"] == 200
    assert {row["source"] for row in history.json()["readings"]} == {"SIMULATED_DEVELOPMENT"}
    assert all(
        row["temperature"] is not None and row["optical_colour_index"] is not None
        for row in history.json()["readings"]
    )

    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    forecast = client.post(
        "/api/v1/forecast",
        json={"node_id": node_id},
        headers={
            "X-HydroGuard-Development-Token": "test-local-token",
            "X-HydroGuard-Development-Role": "STUDENT",
            "X-HydroGuard-Development-Uid": "demo.student@hydroguard.local",
        },
    )
    assert forecast.status_code == 200, forecast.text
    forecast_data = forecast.json()
    rows = history.json()["readings"]
    assert forecast_data["data_source"] == "SIMULATED_DEVELOPMENT"
    forecast_start = datetime.fromisoformat(forecast_data["input_start"].replace("Z", "+00:00"))
    forecast_end = datetime.fromisoformat(forecast_data["input_end"].replace("Z", "+00:00"))
    history_start = datetime.fromisoformat(rows[-30]["timestamp"].replace("Z", "+00:00"))
    history_end = datetime.fromisoformat(rows[-1]["timestamp"].replace("Z", "+00:00"))
    assert forecast_start == history_start
    assert forecast_end == history_end
    assert set(forecast_data["model_predictions"]) == {"LSTM", "PatchTST", "TimeMixer"}
    assert set(forecast_data["prediction"]) == {"pH", "TDS", "turbidity", "temperature", "optical_colour_index"}
    assert set(forecast_data["weights"]) == {"pH", "TDS", "turbidity", "temperature", "optical_colour_index"}
    assert forecast_data["weight_strategy"] in {"initial", "adaptive"}


def _reading_payload(node_id: str, timestamp: datetime, source: str) -> dict:
    return {
        "node_id": node_id,
        "timestamp": timestamp.isoformat(),
        "ph": 7.4,
        "tds": 180.0,
        "turbidity": 1.0,
        "temperature": 22.0,
        "red": 10_000,
        "green": 10_200,
        "blue": 10_100,
        "clear": 11_000,
        "optical_colour_index": 0.1,
        "source": source,
    }


def test_latest_reading_rule_holds_in_development_environment(monkeypatch, authenticated_client):
    """Regression: provenance ordering, not an env-driven exclusion filter.

    Previously ``HYDROGUARD_ENVIRONMENT=development`` made the latest and
    history endpoints filter ``source == "SIMULATED_DEVELOPMENT"``, which
    hid every other stored reading (404) and let a future-dated simulated
    row stand in for live data. The rule must not depend on the shell.
    """
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_SENSOR_API_KEY", "test-sensor-key")
    init_db()
    client = authenticated_client
    headers = {"X-Sensor-Token": "test-sensor-key"}
    now = datetime.now(timezone.utc)

    live_node = "test_reg_live_provenance"
    stored_only_node = "test_reg_stored_readable"
    with get_db_context() as db:
        NodeRepository.get_or_create(db, live_node, "Live Provenance Node", "Test Location")
        NodeRepository.get_or_create(db, stored_only_node, "Stored Only Node", "Test Location")

    # Future-dated simulated sample (inside tolerated clock skew).
    future_simulated = client.post(
        "/api/v1/readings",
        json=_reading_payload(live_node, now + timedelta(hours=6), "SIMULATED_DEVELOPMENT"),
        headers=headers,
    )
    assert future_simulated.status_code == 200, future_simulated.text

    live = client.post(
        "/api/v1/readings",
        json=_reading_payload(live_node, now, "REAL_SENSOR"),
        headers=headers,
    )
    assert live.status_code == 200, live.text

    # A stored sample with unrelated provenance must stay retrievable.
    stored_only = client.post(
        "/api/v1/readings",
        json=_reading_payload(stored_only_node, now, "DEMO"),
        headers=headers,
    )
    assert stored_only.status_code == 200, stored_only.text

    latest = client.get(f"/api/v1/nodes/{live_node}/readings/latest")
    assert latest.status_code == 200, latest.text
    assert latest.json()["source"] == "REAL_SENSOR"
    assert latest.json()["ph"] == 7.4

    readable = client.get(f"/api/v1/nodes/{stored_only_node}/readings/latest")
    assert readable.status_code == 200, readable.text
    assert readable.json()["source"] == "DEMO"

    # Development history is preserved, not rewritten or hidden.
    history = client.get(f"/api/v1/nodes/{live_node}/readings/history")
    assert history.status_code == 200
    assert history.json()["count"] == 2
    assert {row["source"] for row in history.json()["readings"]} == {
        "REAL_SENSOR",
        "SIMULATED_DEVELOPMENT",
    }


def test_reading_rejects_implausibly_future_timestamp(monkeypatch, authenticated_client):
    """A mis-set sensor clock must not publish readings from the future."""
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_SENSOR_API_KEY", "test-sensor-key")
    init_db()
    client = authenticated_client
    node_id = "test_reg_future_rejected"
    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Future Rejected Node", "Test Location")

    response = client.post(
        "/api/v1/readings",
        json=_reading_payload(node_id, datetime.now(timezone.utc) + timedelta(days=3), "REAL_SENSOR"),
        headers={"X-Sensor-Token": "test-sensor-key"},
    )
    assert response.status_code == 422, response.text
    assert "future" in response.text

    latest = client.get(f"/api/v1/nodes/{node_id}/readings/latest")
    assert latest.status_code == 404


if __name__ == "__main__":
    test_readings_api()
