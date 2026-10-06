"""API tests for readings endpoints."""

import sys
from pathlib import Path
from datetime import datetime, timezone

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db, get_db_context
from app.db.repositories import NodeRepository, SensorReadingRepository


def test_readings_api(monkeypatch):
    """Test readings API endpoints."""
    print("\n" + "=" * 70)
    print("TEST: Readings API")
    print("=" * 70)

    # Initialize database
    init_db()

    client = TestClient(app)
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


if __name__ == "__main__":
    test_readings_api()
