"""Opt-in debug identity remains disabled unless explicitly configured."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.db.database import get_db_context
from app.db.hostel_models import HostelFeedback
from app.main import app


def test_development_identity_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")
    monkeypatch.delenv("HYDROGUARD_ENABLE_DEV_AUTH", raising=False)
    monkeypatch.delenv("HYDROGUARD_DEV_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        authenticated_principal(
            authorization=None,
            x_hydroguard_development_token="anything",
            x_hydroguard_development_role="ADMIN",
            x_hydroguard_development_uid="demo.admin@hydroguard.local",
        )
    assert error.value.status_code == 401


def test_development_identity_cannot_be_enabled_in_production(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    with pytest.raises(HTTPException) as error:
        authenticated_principal(
            authorization=None,
            x_hydroguard_development_token="test-local-token",
            x_hydroguard_development_role="ADMIN",
            x_hydroguard_development_uid="demo.admin@hydroguard.local",
        )
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    ("uid", "role"),
    [
        ("demo.student@hydroguard.local", "STUDENT"),
        ("demo.admin@hydroguard.local", "ADMIN"),
    ],
)
def test_development_identity_requires_explicit_flag_and_matching_token(monkeypatch, uid, role):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    principal = authenticated_principal(
        authorization=None,
        x_hydroguard_development_token="test-local-token",
        x_hydroguard_development_role=role,
        x_hydroguard_development_uid=uid,
    )
    assert principal["uid"] == uid
    assert principal["role"] == role
    assert principal["development"] is True


def test_development_identity_rejects_role_uid_mismatch(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    with pytest.raises(HTTPException) as error:
        authenticated_principal(
            authorization=None,
            x_hydroguard_development_token="test-local-token",
            x_hydroguard_development_role="ADMIN",
            x_hydroguard_development_uid="demo.student@hydroguard.local",
        )
    assert error.value.status_code == 401


def test_development_student_headers_authenticate_all_hostel_service_routes(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    headers = {
        "X-HydroGuard-Development-Token": "test-local-token",
        "X-HydroGuard-Development-Role": "STUDENT",
        "X-HydroGuard-Development-Uid": "demo.student@hydroguard.local",
    }
    client = TestClient(app)
    for path in (
        "/api/v1/hostel/issues",
        "/api/v1/hostel/notices",
        "/api/v1/hostel/emergency-contacts",
        "/api/v1/hostel/events",
        "/api/v1/hostel/lost-found",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, f"{path}: {response.text}"

    feedback_id = None
    try:
        response = client.post(
            "/api/v1/hostel/feedback",
            headers=headers,
            json={"category": "Water", "rating": 5, "comment": "Development auth route check"},
        )
        assert response.status_code == 201, response.text
        feedback_id = response.json()["id"]
    finally:
        if feedback_id is not None:
            with get_db_context() as db:
                db.query(HostelFeedback).filter(HostelFeedback.id == feedback_id).delete()
                db.commit()


def test_development_admin_headers_authenticate_admin_hostel_routes(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", "test-local-token")
    headers = {
        "X-HydroGuard-Development-Token": "test-local-token",
        "X-HydroGuard-Development-Role": "ADMIN",
        "X-HydroGuard-Development-Uid": "demo.admin@hydroguard.local",
    }
    client = TestClient(app)
    for path in (
        "/api/v1/hostel/admin/issues/summary",
        "/api/v1/hostel/admin/feedback",
        "/api/v1/hostel/admin/resolution-feedback",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, f"{path}: {response.text}"
