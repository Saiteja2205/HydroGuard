"""Hostel endpoints persist records and enforce per-user/admin boundaries."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.db.database import init_db
from app.main import app


def test_issue_lifecycle_is_persisted_and_owner_scoped(monkeypatch):
    init_db()
    principal = {"uid": "student-1", "role": "STUDENT"}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    client = TestClient(app)

    created = client.post("/api/v1/hostel/issues", json={
        "category": "Plumbing",
        "location": "Block A, room 104",
        "description": "The sink tap is leaking continuously.",
        "severity": "HIGH",
    })
    assert created.status_code == 201
    issue_id = created.json()["id"]
    assert created.json()["status"] == "SUBMITTED"
    assert client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()[0]["to_status"] == "SUBMITTED"

    principal["uid"] = "student-2"
    assert client.get(f"/api/v1/hostel/issues/{issue_id}").status_code == 404

    principal.update(uid="warden-1", role="ADMIN")
    acknowledged = client.patch(f"/api/v1/hostel/issues/{issue_id}/status", json={
        "status": "ACKNOWLEDGED", "comment": "Request acknowledged."
    })
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "ACKNOWLEDGED"

    invalid = client.patch(f"/api/v1/hostel/issues/{issue_id}/status", json={"status": "CLOSED"})
    assert invalid.status_code == 409

    # Students only see verified contacts, even if the development database
    # contains unverified records from earlier test runs.
    principal.update(uid="student-1", role="STUDENT")
    assert all(contact["verified"] for contact in client.get("/api/v1/hostel/emergency-contacts").json())


def test_hostel_services_admin_management_feedback_and_moderation(monkeypatch):
    init_db()
    principal = {"uid": "student-services", "role": "STUDENT"}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    client = TestClient(app)

    notice_payload = {
        "title": "Tank maintenance", "body": "Water service may pause at noon.",
        "category": "MAINTENANCE", "priority": "HIGH",
    }
    assert client.post("/api/v1/hostel/notices", json=notice_payload).status_code == 403
    assert client.get("/api/v1/hostel/events").status_code == 404

    principal.update(uid="warden-services", role="ADMIN")
    notice = client.post("/api/v1/hostel/notices", json=notice_payload)
    assert notice.status_code == 201
    assert client.get("/api/v1/hostel/notices").json()[0]["title"] == "Tank maintenance"
    assert client.put(f"/api/v1/hostel/notices/{notice.json()['id']}", json={
        **notice_payload, "priority": "URGENT",
    }).json()["priority"] == "URGENT"

    unverified = client.post("/api/v1/hostel/emergency-contacts", json={
        "category": "SECURITY", "name": "Unverified contact", "phone": "+91 12345 67891",
    })
    assert unverified.status_code == 201
    assert unverified.json()["verified"] is False
    principal.update(uid="student-services", role="STUDENT")
    assert client.get("/api/v1/hostel/emergency-contacts").json() == []

    principal.update(uid="warden-services", role="ADMIN")
    invalid_contact = client.post("/api/v1/hostel/emergency-contacts", json={
        "category": "AMBULANCE", "name": "Unsupported contact", "phone": "+91 12345 67892",
    })
    assert invalid_contact.status_code == 422
    contact = client.post("/api/v1/hostel/emergency-contacts", json={
        "category": "WARDEN", "name": "Verified Warden", "phone": "+91 12345 67890", "verified": True,
    })
    assert contact.status_code == 201
    assert contact.json()["verified"] is True
    principal.update(uid="student-services", role="STUDENT")
    student_contacts = client.get("/api/v1/hostel/emergency-contacts").json()
    assert all(item["verified"] for item in student_contacts)
    assert all(item["category"] in {"WARDEN", "SECURITY"} for item in student_contacts)
    assert any(item["id"] == contact.json()["id"] for item in student_contacts)

    principal.update(uid="warden-services", role="ADMIN")
    assert client.post("/api/v1/hostel/events", json={}).status_code == 404

    submission = client.post("/api/v1/hostel/lost-found", json={
        "kind": "FOUND", "title": "Keys", "description": "Found a key ring.",
        "category": "Keys", "location": "Library", "item_date": "2026-10-04T09:00:00Z",
    })
    assert submission.status_code == 201
    assert submission.json()["moderation_status"] == "PENDING"
    assert client.patch(f"/api/v1/hostel/lost-found/{submission.json()['id']}/moderation", json={
        "moderation_status": "APPROVED",
    }).status_code == 200

    principal.update(uid="student-services", role="STUDENT")
    feedback = client.post("/api/v1/hostel/feedback", json={
        "category": "Water", "rating": 4, "comment": "Good communication.",
    })
    assert feedback.status_code == 201
    principal.update(uid="warden-services", role="ADMIN")
    assert client.get("/api/v1/hostel/admin/feedback").json()[0]["rating"] == 4

    assert client.delete(f"/api/v1/hostel/notices/{notice.json()['id']}").status_code == 204
    assert client.delete(f"/api/v1/hostel/emergency-contacts/{contact.json()['id']}").status_code == 204
    assert client.delete(f"/api/v1/hostel/emergency-contacts/{unverified.json()['id']}").status_code == 204


def test_resolution_feedback_and_reopen_are_reporter_only(monkeypatch):
    init_db()
    principal = {"uid": "issue-owner", "role": "STUDENT"}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    client = TestClient(app)
    created = client.post("/api/v1/hostel/issues", json={
        "category": "Water", "location": "Block B", "description": "Low water pressure in the shower.",
        "severity": "MEDIUM",
    })
    issue_id = created.json()["id"]
    principal.update(uid="warden", role="ADMIN")
    for status, extra in [
        ("ACKNOWLEDGED", {}), ("ASSIGNED", {"assigned_uid": "staff-1"}),
        ("IN_PROGRESS", {}), ("RESOLVED", {"resolution": "Valve replaced."}),
    ]:
        result = client.patch(f"/api/v1/hostel/issues/{issue_id}/status", json={"status": status, **extra})
        assert result.status_code == 200
    principal.update(uid="another-student", role="STUDENT")
    assert client.post(f"/api/v1/hostel/issues/{issue_id}/feedback", json={"stars": 5}).status_code == 404
    assert client.post(f"/api/v1/hostel/issues/{issue_id}/reopen", json={"reason": "Still leaking."}).status_code == 404
    principal.update(uid="issue-owner", role="STUDENT")
    assert client.post(f"/api/v1/hostel/issues/{issue_id}/feedback", json={"stars": 4, "comment": "Thanks."}).status_code == 201
    reopened = client.post(f"/api/v1/hostel/issues/{issue_id}/reopen", json={"reason": "Leak started again."})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "REOPENED"
    timeline = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    assert timeline[-1]["to_status"] == "REOPENED"
