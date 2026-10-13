"""Sensor-data reads must not be reachable anonymously.

Regression cover for the Stage E finding: ``/nodes``, ``/nodes/{node_id}``,
``/nodes/{node_id}/alerts``, ``/nodes/{node_id}/forecasts``,
``/nodes/{node_id}/model-performance``, ``/nodes/{node_id}/readings/latest``
and ``/nodes/{node_id}/readings/history`` carried no authentication dependency
at all. Probed against a running development backend, a token-less request to
``/nodes/node_overhead_a/readings/latest`` returned HTTP 200 with a full five
parameter reading, while ``/hostel/issues`` on the same server correctly
returned 401 -- so water-quality data was the least protected surface in the
application.

These tests assert the guard itself, which is why they never use the
``authenticated_client`` fixture: that fixture overrides the dependency and
would make every assertion here vacuous.
"""

from fastapi.testclient import TestClient

from app.db.database import get_db_context, init_db
from app.db.repositories import NodeRepository
from app.main import app

NODE_ID = "node_overhead_a"

# Every route that was anonymous before the fix.
PROTECTED_READS = (
    "/api/v1/nodes",
    f"/api/v1/nodes/{NODE_ID}",
    f"/api/v1/nodes/{NODE_ID}/alerts",
    f"/api/v1/nodes/{NODE_ID}/forecasts",
    f"/api/v1/nodes/{NODE_ID}/model-performance",
    f"/api/v1/nodes/{NODE_ID}/readings/latest",
    f"/api/v1/nodes/{NODE_ID}/readings/history",
)

# Header names exactly as app/src/main/.../DevelopmentAuthPolicy.java sends them.
# HTTP header names are case insensitive, so the capitalisation difference
# between client and server is irrelevant.
DEV_TOKEN = "HARNESS-ONLY-not-a-real-secret"
DEV_HEADERS_STUDENT = {
    "X-HydroGuard-Development-Token": DEV_TOKEN,
    "X-HydroGuard-Development-Role": "STUDENT",
    "X-HydroGuard-Development-Uid": "demo.student@hydroguard.local",
}
DEV_HEADERS_ADMIN = {
    "X-HydroGuard-Development-Token": DEV_TOKEN,
    "X-HydroGuard-Development-Role": "ADMIN",
    "X-HydroGuard-Development-Uid": "demo.admin@hydroguard.local",
}


def _enable_development_identity(monkeypatch) -> None:
    """Turn on the debug identity bridge for this test only.

    ``monkeypatch`` restores the previous values afterwards, so neighbouring
    tests keep whatever environment they were written against -- conftest.py
    deliberately never sets ``HYDROGUARD_ENVIRONMENT`` globally.
    """
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    monkeypatch.setenv("HYDROGUARD_ENABLE_DEV_AUTH", "true")
    monkeypatch.setenv("HYDROGUARD_DEV_API_TOKEN", DEV_TOKEN)


def _client() -> TestClient:
    init_db()
    with get_db_context() as db:
        NodeRepository.get_or_create(db, NODE_ID, "Overhead Tank A", "Hostel Block A")
    return TestClient(app)


# --------------------------------------------------------------------------
# The vulnerability this file exists to prevent
# --------------------------------------------------------------------------


def test_every_sensor_read_rejects_an_anonymous_request(monkeypatch):
    _enable_development_identity(monkeypatch)
    client = _client()

    for path in PROTECTED_READS:
        response = client.get(path)
        assert response.status_code == 401, (
            f"{path} answered {response.status_code} without credentials; "
            "sensor data must never be readable anonymously"
        )


def test_anonymous_sensor_reads_leak_no_data_in_the_body(monkeypatch):
    """A rejected read must not quietly return the reading anyway."""
    _enable_development_identity(monkeypatch)
    client = _client()

    response = client.get(f"/api/v1/nodes/{NODE_ID}/readings/latest")
    assert response.status_code == 401
    body = response.text.lower()
    for parameter in ("ph", "tds", "turbidity", "temperature", "optical_colour_index"):
        assert parameter not in body, f"{parameter} leaked in a 401 body: {response.text}"


def test_a_wrong_development_token_is_rejected(monkeypatch):
    """Knowing the header *names* must not be enough."""
    _enable_development_identity(monkeypatch)
    client = _client()

    forged = dict(DEV_HEADERS_STUDENT)
    forged["X-HydroGuard-Development-Token"] = "not-the-configured-token"
    response = client.get(f"/api/v1/nodes/{NODE_ID}/readings/latest", headers=forged)
    assert response.status_code == 401


def test_a_role_uid_mismatch_is_rejected(monkeypatch):
    """A token is only honoured for the identity it was issued for."""
    _enable_development_identity(monkeypatch)
    client = _client()

    mismatched = dict(DEV_HEADERS_STUDENT)
    mismatched["X-HydroGuard-Development-Role"] = "ADMIN"
    response = client.get(f"/api/v1/nodes/{NODE_ID}/readings/latest", headers=mismatched)
    assert response.status_code == 401


def test_student_headers_open_every_sensor_read(monkeypatch):
    """The guard admits an ordinary signed-in student, who needs these screens."""
    _enable_development_identity(monkeypatch)
    client = _client()

    # /alerts, /forecasts and /model-performance assert their node exists first,
    # so seed it and accept either a real 200 or the honest 404 the route gives.
    for path in PROTECTED_READS:
        response = client.get(path, headers=DEV_HEADERS_STUDENT)
        assert response.status_code in (200, 404), (
            f"{path} answered {response.status_code} to a valid student"
        )


def test_admin_headers_also_open_every_sensor_read(monkeypatch):
    _enable_development_identity(monkeypatch)
    client = _client()

    for path in PROTECTED_READS:
        response = client.get(path, headers=DEV_HEADERS_ADMIN)
        assert response.status_code in (200, 404)


# --------------------------------------------------------------------------
# Contract notes: what is intentionally still open, and why
# --------------------------------------------------------------------------


def test_health_stays_public_because_it_is_a_liveness_probe(monkeypatch):
    """A readiness probe cannot require the credential it is checking."""
    _enable_development_identity(monkeypatch)
    response = _client().get("/api/v1/health")
    assert response.status_code == 200


def test_sensor_ingestion_still_requires_the_separate_sensor_key(monkeypatch):
    """Reading a value and publishing one use different credentials on purpose.

    A student token must never be able to write a measurement, so the sensor
    ingest route keeps ``require_sensor_key`` and is not covered by the
    principal guard added here.
    """
    _enable_development_identity(monkeypatch)
    client = _client()

    payload = {
        "node_id": NODE_ID,
        "timestamp": "2026-01-01T00:00:00Z",
        "ph": 7.0,
        "tds": 300.0,
        "turbidity": 1.0,
        "temperature": 20.0,
    }
    response = client.post("/api/v1/readings", json=payload, headers=DEV_HEADERS_STUDENT)
    assert response.status_code in (401, 503), (
        f"a student token reached sensor ingestion: {response.status_code}"
    )


def test_unconfigured_sensor_key_is_reported_not_silently_accepted(monkeypatch):
    """With no key configured the ingest route must refuse, not open up."""
    _enable_development_identity(monkeypatch)
    monkeypatch.delenv("HYDROGUARD_SENSOR_API_KEY", raising=False)

    response = _client().post(
        "/api/v1/readings",
        json={
            "node_id": NODE_ID,
            "timestamp": "2026-01-01T00:00:00Z",
            "ph": 7.0,
            "tds": 300.0,
            "turbidity": 1.0,
            "temperature": 20.0,
        },
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()
