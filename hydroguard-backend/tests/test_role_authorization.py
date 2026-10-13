"""Student/admin authorization is enforced by the backend on every privileged route.

A hidden control in the app is not authorization: these tests assert that a STUDENT
principal is denied on each admin-only operation and that an ADMIN principal is
allowed, so the UI role gate and the server-side gate cannot drift apart.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.db.database import get_db_context, init_db
from app.main import app
from app.db.models import ThresholdConfig


@pytest.fixture(autouse=True)
def _restore_thresholds():
    """The admin probe mutates the shared threshold override; roll that back.

    The suite runs against one database, so leaving the override in place would
    make an unrelated defaults test fail on the next run.
    """
    init_db()
    with get_db_context() as db:
        snapshot = [
            (row.parameter, row.min_value, row.max_value)
            for row in db.query(ThresholdConfig).all()
        ]
    yield
    with get_db_context() as db:
        db.query(ThresholdConfig).delete()
        for parameter, min_value, max_value in snapshot:
            db.add(ThresholdConfig(parameter=parameter, min_value=min_value, max_value=max_value))
        # get_db_context() closes without committing, so persist explicitly.
        db.commit()


def _client(monkeypatch, role: str, uid: str | None = None) -> TestClient:
    init_db()
    principal = {"uid": uid or f"authz-{role.lower()}", "role": role}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    return TestClient(app)


# (method, path, json body) for every operation the app gates behind an admin role.
ADMIN_ONLY_OPERATIONS = [
    ("PATCH", "/api/v1/thresholds", {"thresholds": {"tds": {"max": 250.0}}}),
    ("POST", "/api/v1/nodes", {"node_id": "authz_probe_node", "name": "Probe", "location": "Lab"}),
    ("PATCH", "/api/v1/nodes/node_overhead_a/status", {"status": "offline"}),
    ("POST", "/api/v1/alerts", {"node_id": "node_overhead_a", "parameter": "ph", "value": 9.9}),
    ("POST", "/api/v1/admin/users/invite", {"email": "invitee@vrsec.ac.in", "role": "STUDENT"}),
    ("POST", "/api/v1/hostel/notices", {"title": "Probe", "body": "Probe notice"}),
    ("POST", "/api/v1/hostel/emergency-contacts", {"label": "Warden", "phone": "100"}),
    ("PATCH", "/api/v1/hostel/lost-found/missing-id/moderation", {"moderation_status": "APPROVED"}),
    ("PATCH", "/api/v1/hostel/issues/00000000-0000-0000-0000-000000000000/status", {"status": "RESOLVED", "resolution": "Probe"}),
    ("GET", "/api/v1/hostel/admin/issues/summary", {}),
]


def test_student_is_denied_every_admin_operation(monkeypatch):
    """A verified student session must never be able to mutate admin data."""
    client = _client(monkeypatch, "STUDENT")
    for method, path, body in ADMIN_ONLY_OPERATIONS:
        response = client.request(method, path, json=body)
        assert response.status_code == 403, (
            f"STUDENT was not denied {method} {path}: got {response.status_code}"
        )


def test_admin_is_authorized_for_admin_operations(monkeypatch):
    """The same operations succeed for a verified administrator."""
    client = _client(monkeypatch, "ADMIN")
    denied = []
    for method, path, body in ADMIN_ONLY_OPERATIONS:
        response = client.request(method, path, json=body)
        if response.status_code == 403:
            denied.append(f"{method} {path} -> {response.status_code}")
    assert not denied, "ADMIN was unexpectedly denied: " + "; ".join(denied)


def test_unknown_role_is_rejected(monkeypatch):
    """A principal with an unrecognized role gains no privileged access."""
    client = _client(monkeypatch, "SUPERUSER")
    for method, path, body in ADMIN_ONLY_OPERATIONS:
        response = client.request(method, path, json=body)
        assert response.status_code == 403, (
            f"unknown role was not denied {method} {path}: got {response.status_code}"
        )


def test_unauthenticated_request_is_rejected(monkeypatch):
    """No principal override at all -> the request never reaches a handler."""
    init_db()
    client = TestClient(app)
    for method, path, body in ADMIN_ONLY_OPERATIONS:
        response = client.request(method, path, json=body)
        assert response.status_code in (401, 403), (
            f"unauthenticated {method} {path} was not rejected: {response.status_code}"
        )


def test_students_cannot_list_feedback_or_admin_user_directory(monkeypatch):
    """Read routes that expose other people's data are admin-only too."""
    client = _client(monkeypatch, "STUDENT")
    assert client.get("/api/v1/hostel/admin/feedback").status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403

    admin = _client(monkeypatch, "ADMIN")
    assert admin.get("/api/v1/hostel/admin/feedback").status_code == 200


def test_student_cannot_change_issue_status_of_another_reporter(monkeypatch):
    """Issue status transitions are admin-scoped, not open to every student."""
    client = _client(monkeypatch, "STUDENT")
    response = client.patch(
        "/api/v1/hostel/issues/00000000-0000-0000-0000-000000000000/status",
        json={"status": "RESOLVED", "resolution": "Probe"},
    )
    assert response.status_code == 403
