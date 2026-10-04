"""API tests for forecasts endpoints."""

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
from app.core.auth import require_student_or_admin


def test_forecasts_api(monkeypatch):
    """Test forecasts API endpoints."""
    print("\n" + "=" * 70)
    print("TEST: Forecasts API")
    print("=" * 70)

    # Initialize database
    init_db()

    client = TestClient(app)
    monkeypatch.setitem(app.dependency_overrides, require_student_or_admin, lambda: {"uid": "test-user", "role": "STUDENT"})

    # Create test node (use get_or_create to avoid conflicts)
    with get_db_context() as db:
        NodeRepository.get_or_create(
            db=db,
            node_id="test_api_node_2",
            name="Test API Node 2",
            location="Test Location",
        )

    # Test GET forecasts
    print("\n1. Testing GET /nodes/{node_id}/forecasts:")
    response = client.get("/api/v1/nodes/test_api_node_2/forecasts?limit=10")
    assert response.status_code == 200
    result = response.json()
    assert "forecasts" in result
    assert "count" in result
    print(f"   [OK] GET forecasts succeeded: {result['count']} forecasts")

    # Test GET model performance
    print("\n2. Testing GET /nodes/{node_id}/model-performance:")
    response = client.get("/api/v1/nodes/test_api_node_2/model-performance")
    assert response.status_code == 200
    result = response.json()
    assert "node_id" in result
    assert "performance" in result
    print(f"   [OK] GET model performance succeeded")

    # Insufficient history is rejected before node lookup/model loading, with
    # an explicit explanation instead of synthesizing observations.
    recent = datetime.now(timezone.utc).isoformat()
    response = client.post("/api/v1/forecast", json={
        "node_id": "test_api_node_2",
        "readings": [{
            "timestamp": recent,
            "pH": 7.0,
            "TDS": 180.0,
            "turbidity": 1.0,
            "temperature": 22.0,
                "optical_colour_index": 0.5,
            "source": "DEMO",
        }],
    })
    assert response.status_code == 422
    assert "At least 30" in response.json()["detail"]
    print("   [OK] Insufficient forecast history rejected explicitly")

    print("\n[OK] Forecasts API test passed")


if __name__ == "__main__":
    test_forecasts_api()
