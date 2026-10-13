"""Issue lifecycle: valid transitions, invalid transitions, roles, concurrency.

The administrator workflow has to survive a real support conversation:
acknowledge, start work, park while waiting for a resident, resolve with a
summary, and reopen when the problem returns. These tests exercise the very
endpoints the Android Hostel Operations screen calls, so a regression here is
the same regression an administrator would hit on the phone.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.api.hostel import ISSUE_TRANSITIONS, ISSUE_STATUS_LABELS, valid_next_statuses
from app.core.auth import authenticated_principal
from app.db.database import init_db
from app.main import app


ISSUE_BODY = {
    "category": "Plumbing",
    "location": "Hostel Block, room 104",
    "description": "The sink tap is leaking continuously.",
    "severity": "HIGH",
}


def _session(monkeypatch, uid: str, role: str) -> TestClient:
    init_db()
    principal = {"uid": uid, "role": role}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    return TestClient(app)


def _create(client: TestClient) -> str:
    created = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _patch(client: TestClient, issue_id: str, **body):
    return client.patch(f"/api/v1/hostel/issues/{issue_id}/status", json=body)


def test_admin_can_walk_the_whole_lifecycle_to_closed(monkeypatch):
    """Every documented step is reachable in order and the final state sticks."""
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)

    steps = [
        {"status": "ACKNOWLEDGED", "comment": "Seen it, checking the line."},
        {"status": "IN_PROGRESS"},
        {"status": "WAITING", "comment": "Waiting for a replacement tap from the store."},
        {"status": "IN_PROGRESS", "comment": "Part arrived, work resumed."},
        {"status": "RESOLVED", "resolution": "Tap cartridge replaced and tested."},
        {"status": "CLOSED"},
    ]
    expected = [
        "ACKNOWLEDGED", "IN_PROGRESS", "WAITING", "IN_PROGRESS", "RESOLVED", "CLOSED",
    ]

    for step, want in zip(steps, expected):
        response = _patch(client, issue_id, **step)
        assert response.status_code == 200, f"{step} -> {response.status_code} {response.text}"
        assert response.json()["status"] == want
        # Server confirmation is the only source of truth for the client.
        assert response.json()["updated_at"] >= response.json()["created_at"]

    # The state survives a fresh read, i.e. it was persisted, not just echoed.
    reloaded = client.get(f"/api/v1/hostel/issues/{issue_id}")
    assert reloaded.json()["status"] == "CLOSED"
    assert reloaded.json()["resolution"] == "Tap cartridge replaced and tested."

    timeline = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    assert [event["to_status"] for event in timeline] == [
        "SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS", "WAITING",
        "IN_PROGRESS", "RESOLVED", "CLOSED",
    ]
    assert all(event["created_at"] for event in timeline)


def test_invalid_transitions_are_rejected_with_409(monkeypatch):
    """Skipping steps or reversing the lifecycle must never silently succeed."""
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)

    assert _patch(client, issue_id, status="RESOLVED", resolution="Nope").status_code == 409
    assert _patch(client, issue_id, status="CLOSED").status_code == 409
    assert _patch(client, issue_id, status="SUBMITTED").status_code == 409

    assert _patch(client, issue_id, status="ACKNOWLEDGED").status_code == 200
    assert _patch(client, issue_id, status="CLOSED").status_code == 409
    assert _patch(client, issue_id, status="SUBMITTED").status_code == 409

    # The rejected attempts must not have moved or recorded anything.
    timeline = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    assert [event["to_status"] for event in timeline] == ["SUBMITTED", "ACKNOWLEDGED"]


def test_repeating_the_current_status_does_not_add_a_second_event(monkeypatch):
    """Double-tapping the same action is a no-op, not a duplicate transition."""
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)

    assert _patch(client, issue_id, status="ACKNOWLEDGED").status_code == 200
    repeat = _patch(client, issue_id, status="ACKNOWLEDGED")
    assert repeat.status_code == 409
    assert "already ACKNOWLEDGED" in repeat.json()["detail"]

    events = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    assert len(events) == 2, [event["to_status"] for event in events]

    # Re-running the whole sequence twice still yields exactly one transition.
    again = _patch(client, issue_id, status="ACKNOWLEDGED")
    assert again.status_code == 409
    assert len(client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()) == 2


def test_waiting_records_the_optional_reason_and_resolution_is_required_to_resolve(monkeypatch):
    """Parking an issue keeps the reason; resolving without a summary is a 422."""
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)

    assert _patch(client, issue_id, status="ACKNOWLEDGED").status_code == 200
    waiting = _patch(client, issue_id, status="WAITING")
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "WAITING"

    missing_summary = _patch(client, issue_id, status="RESOLVED")
    assert missing_summary.status_code == 422

    resolved = _patch(client, issue_id, status="RESOLVED", resolution="Pipe joint resealed.")
    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "Pipe joint resealed."

    events = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    waiting_events = [event for event in events if event["to_status"] == "WAITING"]
    assert len(waiting_events) == 1
    assert waiting_events[0]["from_status"] == "ACKNOWLEDGED"
    assert waiting_events[0]["comment"] is None


def test_waiting_reason_is_persisted_when_provided(monkeypatch):
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)
    _patch(client, issue_id, status="WAITING", comment="Awaiting the resident's room number.")

    events = client.get(f"/api/v1/hostel/issues/{issue_id}/timeline").json()
    assert events[-1]["comment"] == "Awaiting the resident's room number."


def test_only_an_administrator_can_change_a_status(monkeypatch):
    """Students may read their own issue status but never transition it."""
    client = _session(monkeypatch, "student-owner", "STUDENT")
    issue_id = _create(client)

    denied = _patch(client, issue_id, status="ACKNOWLEDGED")
    assert denied.status_code == 403

    assert client.get(f"/api/v1/hostel/issues/{issue_id}").json()["status"] == "SUBMITTED"


def test_admin_can_reopen_another_students_resolved_issue(monkeypatch):
    """Wardens own the whole queue, including complaints they did not file."""
    student = _session(monkeypatch, "student-owner", "STUDENT")
    issue_id = _create(student)

    admin = _session(monkeypatch, "warden", "ADMIN")
    assert _patch(admin, issue_id, status="ACKNOWLEDGED").status_code == 200
    assert _patch(admin, issue_id, status="IN_PROGRESS").status_code == 200
    assert _patch(
        admin, issue_id, status="RESOLVED", resolution="Fixed."
    ).status_code == 200

    reopened = admin.post(
        f"/api/v1/hostel/issues/{issue_id}/reopen",
        json={"reason": "The leak returned overnight."},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "REOPENED"

    # ...and can then put it back to work through the normal transition table.
    assert _patch(admin, issue_id, status="IN_PROGRESS").status_code == 200

    # An unrelated student still cannot touch it.
    stranger = _session(monkeypatch, "stranger", "STUDENT")
    assert stranger.post(
        f"/api/v1/hostel/issues/{issue_id}/reopen", json={"reason": "Not mine to reopen."}
    ).status_code == 404


def test_reopening_twice_is_rejected(monkeypatch):
    client = _session(monkeypatch, "warden", "ADMIN")
    issue_id = _create(client)
    _patch(client, issue_id, status="ACKNOWLEDGED")
    _patch(client, issue_id, status="IN_PROGRESS")
    _patch(client, issue_id, status="RESOLVED", resolution="Fixed.")

    first = client.post(f"/api/v1/hostel/issues/{issue_id}/reopen", json={"reason": "Returned again."})
    assert first.status_code == 200
    second = client.post(f"/api/v1/hostel/issues/{issue_id}/reopen", json={"reason": "Returned again."})
    assert second.status_code == 409


def test_workflow_endpoint_is_authenticated_and_matches_the_transition_table(monkeypatch):
    """Clients build their buttons from this payload, so it must be exact."""
    client = _session(monkeypatch, "student", "STUDENT")
    response = client.get("/api/v1/hostel/issues/workflow")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["initial_status"] == "SUBMITTED"
    assert payload["transitions"] == {
        status: sorted(targets) for status, targets in ISSUE_TRANSITIONS.items()
    }
    assert payload["labels"] == ISSUE_STATUS_LABELS
    assert payload["open_label"] == "SUBMITTED"
    assert payload["requires"] == {"resolution": ["RESOLVED"], "assigned_uid": ["ASSIGNED"]}
    assert "WAITING" in payload["statuses"]
    # SUBMITTED must present as "Open" to administrators.
    assert payload["labels"]["SUBMITTED"] == "Open"


def test_workflow_endpoint_rejects_anonymous_callers():
    """No principal override at all -> the handler is never reached."""
    init_db()
    assert TestClient(app).get("/api/v1/hostel/issues/workflow").status_code == 401


def test_next_status_helper_refuses_impossible_moves():
    """The pure helper used by clients mirrors ISSUE_TRANSITIONS exactly."""
    assert valid_next_statuses("SUBMITTED") == ["ACKNOWLEDGED", "IN_PROGRESS", "WAITING"]
    assert valid_next_statuses("WAITING") == ["ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"]
    assert valid_next_statuses("RESOLVED") == ["CLOSED", "REOPENED"]
    assert valid_next_statuses("CLOSED") == ["REOPENED"]
    assert valid_next_statuses("REOPENED") == ["ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "WAITING"]
    assert valid_next_statuses("IN_PROGRESS") == ["RESOLVED", "WAITING"]
    # Every advertised target is itself a known status.
    known = set(ISSUE_TRANSITIONS)
    for sources in ISSUE_TRANSITIONS.values():
        assert sources <= known, sources - known


def test_student_sees_only_their_own_issue_status(monkeypatch):
    """Ownership rules are unchanged: another student's complaint is invisible."""
    owner = _session(monkeypatch, "owner", "STUDENT")
    issue_id = _create(owner)

    other = _session(monkeypatch, "other", "STUDENT")
    assert other.get(f"/api/v1/hostel/issues/{issue_id}").status_code == 404
    assert other.get("/api/v1/hostel/issues").json() == []

    admin = _session(monkeypatch, "warden", "ADMIN")
    assert admin.get("/api/v1/hostel/issues").json()[0]["id"] == issue_id
