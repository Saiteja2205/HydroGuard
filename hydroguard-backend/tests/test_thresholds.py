"""API tests for configurable threshold endpoints."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.core.auth import authenticated_principal
from app.db.database import get_db_context, init_db
from app.services.alert_service import AlertService


import pytest
from app.db.models import ThresholdConfig


@pytest.fixture(autouse=True)
def clean_thresholds():
    init_db()
    with get_db_context() as db:
        db.query(ThresholdConfig).delete()
        db.commit()
    yield
    with get_db_context() as db:
        db.query(ThresholdConfig).delete()
        db.commit()


def _client(monkeypatch, role: str) -> TestClient:
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": f"test-{role.lower()}", "role": role},
    )
    return TestClient(app)



def test_get_thresholds_returns_defaults(monkeypatch):
    client = _client(monkeypatch, "STUDENT")
    response = client.get("/api/v1/thresholds")
    assert response.status_code == 200
    thresholds = {item["parameter"]: item for item in response.json()["thresholds"]}
    assert thresholds["ph"]["min"] == 6.5
    assert thresholds["ph"]["max"] == 8.5
    assert thresholds["tds"]["max"] == 500.0


def test_admin_can_update_thresholds_and_alerts_use_them(monkeypatch):
    client = _client(monkeypatch, "ADMIN")
    response = client.patch(
        "/api/v1/thresholds",
        json={"thresholds": {"tds": {"max": 250.0}, "ph": {"min": 6.0, "max": 8.0}}},
    )
    assert response.status_code == 200
    thresholds = {item["parameter"]: item for item in response.json()["thresholds"]}
    assert thresholds["tds"]["max"] == 250.0
    assert thresholds["ph"]["min"] == 6.0

    with get_db_context() as db:
        effective = AlertService.get_effective_thresholds(db)
        assert effective["tds"]["max"] == 250.0
        assert effective["ph"]["max"] == 8.0


def test_student_cannot_update_thresholds(monkeypatch):
    client = _client(monkeypatch, "STUDENT")
    response = client.patch("/api/v1/thresholds", json={"thresholds": {"tds": {"max": 100.0}}})
    assert response.status_code == 403


def test_threshold_validation(monkeypatch):
    client = _client(monkeypatch, "ADMIN")
    response = client.patch(
        "/api/v1/thresholds",
        json={"thresholds": {"temperature": {"min": 30.0, "max": 15.0}}},
    )
    assert response.status_code == 422
    response = client.patch("/api/v1/thresholds", json={"thresholds": {"temperature": {}}})
    assert response.status_code == 422
