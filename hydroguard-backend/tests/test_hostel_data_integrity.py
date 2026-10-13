"""Data-integrity guarantees for hostel records.

These tests pin the behaviour the app relies on to render each record exactly once:
every record carries a stable unique id, genuinely separate complaints are kept even
when their text matches, and repeated identical submissions do not keep appending
duplicate rows.
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.db.database import init_db
from app.main import app


def _client(monkeypatch, uid: str, role: str = "STUDENT") -> TestClient:
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": uid, "role": role},
    )
    return TestClient(app)


ISSUE_BODY = {
    "category": "Plumbing",
    "location": "Block A, room 104",
    "description": "The sink tap is leaking continuously.",
    "severity": "HIGH",
}


def test_each_issue_has_a_stable_unique_id(monkeypatch):
    """Ids are the render key: they must be present, non-empty and unique."""
    client = _client(monkeypatch, "integrity-unique")
    ids = set()
    for _ in range(3):
        created = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
        assert created.status_code == 201
        issue_id = created.json()["id"]
        assert issue_id
        assert issue_id not in ids, "issue ids must not repeat"
        ids.add(issue_id)

    listed = {row["id"] for row in client.get("/api/v1/hostel/issues").json()}
    assert ids <= listed, "every created issue must appear exactly once when listed"
    assert len(listed) == len(client.get("/api/v1/hostel/issues").json()), (
        "listing must not return duplicate rows for the same record"
    )


def test_identical_descriptions_from_one_reporter_are_kept_separate(monkeypatch):
    """Matching text alone must not collapse distinct submissions into one."""
    client = _client(monkeypatch, "integrity-separate")
    first = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
    second = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    listed = client.get("/api/v1/hostel/issues").json()
    matching = [row for row in listed if row["description"] == ISSUE_BODY["description"]]
    assert len(matching) >= 2, "two separate submissions with equal text must both survive"


def test_issue_records_are_owner_scoped(monkeypatch):
    """One student's reports are not visible to another student."""
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-owner-a", "role": "STUDENT"},
    )
    client = TestClient(app)
    created = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
    assert created.status_code == 201
    issue_id = created.json()["id"]
    owner_ids = {row["id"] for row in client.get("/api/v1/hostel/issues").json()}
    assert issue_id in owner_ids

    # Switch the acting principal: a different student must not see the report.
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-owner-b", "role": "STUDENT"},
    )
    other_ids = {row["id"] for row in client.get("/api/v1/hostel/issues").json()}
    assert issue_id not in other_ids, "another student must not see this report"


def test_admin_sees_every_report(monkeypatch):
    """An administrator sees all reports, including the student's."""
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-admin-view", "role": "STUDENT"},
    )
    client = TestClient(app)
    created = client.post("/api/v1/hostel/issues", json=ISSUE_BODY)
    issue_id = created.json()["id"]

    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-admin-view", "role": "ADMIN"},
    )
    admin_ids = {row["id"] for row in client.get("/api/v1/hostel/issues").json()}
    assert issue_id in admin_ids


def test_issue_created_at_is_never_empty(monkeypatch):
    """A missing submission timestamp would fabricate freshness in the UI."""
    client = _client(monkeypatch, "integrity-timestamps")
    created = client.post("/api/v1/hostel/issues", json=ISSUE_BODY).json()
    assert created.get("created_at"), "the API must always return a submission timestamp"


def test_lost_found_repeat_submission_is_idempotent(monkeypatch):
    """An identical repeat from the same reporter does not append a duplicate row."""
    client = _client(monkeypatch, "integrity-lostfound")
    body = {
        "kind": "FOUND",
        "title": "Blue water bottle",
        "description": "Left near the Block B water cooler.",
        "category": "Other",
        "location": "Block B",
        "item_date": "2026-10-05T10:00:00Z",
    }
    first = client.post("/api/v1/hostel/lost-found", json=body)
    assert first.status_code == 201
    repeat = client.post("/api/v1/hostel/lost-found", json=body)
    assert repeat.status_code == 201
    assert first.json()["id"] == repeat.json()["id"], (
        "an identical repeat submission must reuse the original record, not create a new one"
    )


def test_issue_feedback_stores_the_human_readable_fields(monkeypatch):
    """Feedback keeps rating and comment so the UI need not show a raw id alone."""
    init_db()
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-feedback", "role": "STUDENT"},
    )
    client = TestClient(app)
    issue_id = client.post("/api/v1/hostel/issues", json=ISSUE_BODY).json()["id"]

    # Resolution feedback is only accepted once the issue is resolved.
    early = client.post(
        f"/api/v1/hostel/issues/{issue_id}/feedback",
        json={"stars": 4, "comment": "Thanks."},
    )
    assert early.status_code == 409, "feedback before resolution must be refused"

    # An admin walks the issue through its legal lifecycle to RESOLVED, which
    # makes feedback available to the owner. SUBMITTED -> RESOLVED directly is
    # correctly refused, so each intermediate state is applied in turn.
    for status, body in (
        ("ACKNOWLEDGED", {}),
        ("IN_PROGRESS", {}),
        ("RESOLVED", {"resolution": "Tap replaced."}),
    ):
        monkeypatch.setitem(
            app.dependency_overrides,
            authenticated_principal,
            lambda: {"uid": "integrity-feedback", "role": "ADMIN"},
        )
        step = client.patch(
            f"/api/v1/hostel/issues/{issue_id}/status",
            json={"status": status, **body},
        )
        assert step.status_code == 200, f"transition to {status} failed: {step.text}"

    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "integrity-feedback", "role": "STUDENT"},
    )
    response = client.post(
        f"/api/v1/hostel/issues/{issue_id}/feedback",
        json={"stars": 4, "comment": "Thanks."},
    )
    assert response.status_code == 201
    record = response.json()
    assert record["stars"] == 4
    assert record["comment"] == "Thanks."
    assert record.get("created_at"), "feedback must carry a submission timestamp"

    # A second feedback for the same issue must not create a duplicate record.
    duplicate = client.post(
        f"/api/v1/hostel/issues/{issue_id}/feedback",
        json={"stars": 2, "comment": "Changed my mind."},
    )
    assert duplicate.status_code == 409, "repeat feedback must not append a duplicate"
