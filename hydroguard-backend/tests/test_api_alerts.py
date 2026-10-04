"""API tests for alerts endpoints."""

import sys
from pathlib import Path
from datetime import datetime, timezone

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db, get_db_context
from app.db.repositories import NodeRepository
from app.core.auth import authenticated_principal


def test_alerts_api(monkeypatch):
    """Test alerts API endpoints."""
    print("\n" + "=" * 70)
    print("TEST: Alerts API")
    print("=" * 70)

    # Initialize database
    init_db()

    client = TestClient(app)
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: {"uid": "test-admin", "role": "ADMIN"})

    # Create test node (use get_or_create to avoid conflicts)
    with get_db_context() as db:
        NodeRepository.get_or_create(
            db=db,
            node_id="test_api_node_3",
            name="Test API Node 3",
            location="Test Location",
        )

    # Test POST alert
    print("\n1. Testing POST /alerts:")
    alert_data = {
        "node_id": "test_api_node_3",
        "parameter": "pH",
        "value": 6.0,
        "threshold": 6.5,
        "severity": "WARNING",
        "message": "pH below minimum threshold",
    }
    response = client.post("/api/v1/alerts", json=alert_data)
    assert response.status_code == 200
    result = response.json()
    assert result["node_id"] == "test_api_node_3"
    assert result["parameter"] == "pH"
    print(f"   [OK] POST /alerts succeeded")

    # Test GET alerts
    print("\n2. Testing GET /nodes/{node_id}/alerts:")
    response = client.get("/api/v1/nodes/test_api_node_3/alerts?limit=10")
    assert response.status_code == 200
    result = response.json()
    assert "alerts" in result
    assert "count" in result
    assert result["count"] >= 1
    print(f"   [OK] GET alerts succeeded: {result['count']} alerts")

    # Test GET alerts with status filter
    print("\n3. Testing GET alerts with status filter:")
    response = client.get("/api/v1/nodes/test_api_node_3/alerts?status=ACTIVE&limit=10")
    assert response.status_code == 200
    result = response.json()
    assert result["count"] >= 1
    print(f"   [OK] GET alerts with filter succeeded")

    # Test PATCH alert status
    print("\n4. Testing PATCH /alerts/{alert_id}:")
    alert_id = result["alerts"][0]["id"]
    response = client.patch(f"/api/v1/alerts/{alert_id}?status=ACKNOWLEDGED")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ACKNOWLEDGED"
    print(f"   [OK] PATCH alert status succeeded")

    print("\n[OK] Alerts API test passed")


if __name__ == "__main__":
    test_alerts_api()
