"""Firebase Admin initialization and server-owned role policy tests."""

import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import auth


def test_firebase_app_uses_application_default_credentials_for_configured_project(monkeypatch):
    project_id = "hydroguard-4a606"
    credentials = object()
    app = SimpleNamespace(project_id=project_id)
    calls = {}

    def initialize_app(credential, options, name):
        calls.update(credential=credential, options=options, name=name)
        return app

    firebase_admin = SimpleNamespace(
        get_app=lambda name: (_ for _ in ()).throw(ValueError("not initialized")),
        initialize_app=initialize_app,
        credentials=SimpleNamespace(ApplicationDefault=lambda: credentials),
    )
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", project_id)
    monkeypatch.setitem(sys.modules, "firebase_admin", firebase_admin)

    assert auth._firebase_app() is app
    assert calls == {
        "credential": credentials,
        "options": {"projectId": project_id},
        "name": "hydroguard-api",
    }


def test_firebase_app_rejects_an_already_initialized_different_project(monkeypatch):
    firebase_admin = SimpleNamespace(
        get_app=lambda name: SimpleNamespace(project_id="unexpected-project"),
        credentials=SimpleNamespace(),
    )
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setitem(sys.modules, "firebase_admin", firebase_admin)

    with pytest.raises(HTTPException) as error:
        auth._firebase_app()

    assert error.value.status_code == 503


def test_bootstrap_identity_accepts_verified_id_token_without_role_claim(monkeypatch):
    app = object()
    calls = {}

    def verify_id_token(token, app, check_revoked, clock_skew_seconds=0):
        calls.update(token=token, app=app, check_revoked=check_revoked, clock_skew_seconds=clock_skew_seconds)
        return {"uid": "firebase-uid", "email": "student@college.edu", "email_verified": True}

    monkeypatch.setattr(auth, "_firebase_app", lambda: app)
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(auth=SimpleNamespace(verify_id_token=verify_id_token)),
    )

    identity = auth.verified_firebase_identity(authorization="Bearer firebase-id-token")

    assert identity == {"uid": "firebase-uid", "email": "student@college.edu", "email_verified": True}
    assert calls == {
        "token": "firebase-id-token",
        "app": app,
        "check_revoked": True,
        "clock_skew_seconds": 5,
    }


def test_database_role_overrides_client_token_claim(monkeypatch):
    student_record = SimpleNamespace(
        id=1,
        firebase_uid="firebase-uid",
        email="student@college.edu",
        role="STUDENT",
        status="ACTIVE",
        display_name="Student",
    )

    class Query:
        def filter_by(self, **kwargs):
            assert kwargs == {"firebase_uid": "firebase-uid"}
            return self

        def one_or_none(self):
            return student_record

    class Database:
        def query(self, model):
            assert model is auth.HydroGuardUser
            return Query()

    principal = auth._database_principal(
        {
            "uid": "firebase-uid",
            "email": "student@college.edu",
            "email_verified": True,
            "role": "ADMIN",
        },
        Database(),
    )

    assert principal["role"] == "STUDENT"


def test_database_principal_rejects_missing_account_record():
    class Query:
        def filter_by(self, **kwargs):
            return self

        def one_or_none(self):
            return None

    class Database:
        def query(self, model):
            return Query()

    with pytest.raises(HTTPException) as error:
        auth._database_principal(
            {"uid": "firebase-uid", "email": "new@college.edu"},
            Database(),
        )

    assert error.value.status_code == 403


def test_missing_and_invalid_bearer_tokens_are_rejected(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        auth.verified_firebase_identity(authorization=None)
    assert missing.value.status_code == 401

    monkeypatch.setattr(auth, "_firebase_app", lambda: object())

    def reject_token(*args, **kwargs):
        raise ValueError("invalid token")

    monkeypatch.setitem(sys.modules, "firebase_admin", SimpleNamespace(auth=SimpleNamespace(verify_id_token=reject_token)))
    with pytest.raises(HTTPException) as invalid:
        auth.verified_firebase_identity(authorization="Bearer invalid")
    assert invalid.value.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"uid": "firebase-uid", "email": "student@college.edu", "email_verified": False},
        {"uid": "firebase-uid", "email": "student@college.edu", "email_verified": True},
    ],
)
def test_verified_identity_rejects_unverified_or_missing_firebase_token(monkeypatch, claims):
    monkeypatch.setattr(auth, "_firebase_app", lambda: object())
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(auth=SimpleNamespace(verify_id_token=lambda *args, **kwargs: claims)),
    )
    if claims["email_verified"]:
        claims.pop("email")
    with pytest.raises(HTTPException) as error:
        auth.verified_firebase_identity(authorization="Bearer firebase-id-token")
    assert error.value.status_code in {401, 403}


def test_student_or_admin_dependency_requires_supported_claim_and_preserves_admin_claim():
    assert auth.require_student_or_admin({"uid": "student-uid", "role": "student"}) == {
        "uid": "student-uid",
        "role": "STUDENT",
    }
    assert auth.require_student_or_admin({"uid": "admin-uid", "role": "admin"}) == {
        "uid": "admin-uid",
        "role": "ADMIN",
    }

    with pytest.raises(HTTPException) as error:
        auth.require_student_or_admin({"uid": "unassigned-uid"})
    assert error.value.status_code == 403


def test_student_or_admin_dependency_rejects_unrecognized_claim():
    with pytest.raises(HTTPException) as error:
        auth.require_student_or_admin({"uid": "user-uid", "role": "OWNER"})

    assert error.value.status_code == 403


def test_verified_identity_respects_custom_clock_skew_seconds(monkeypatch):
    app = object()
    calls = {}

    def verify_id_token(token, app, check_revoked, clock_skew_seconds=0):
        calls.update(clock_skew_seconds=clock_skew_seconds)
        return {"uid": "test-uid", "email": "student@vrsec.ac.in", "email_verified": True}

    monkeypatch.setenv("HYDROGUARD_FIREBASE_CLOCK_SKEW_SECONDS", "8")
    monkeypatch.setattr(auth, "_firebase_app", lambda: app)
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(auth=SimpleNamespace(verify_id_token=verify_id_token)),
    )

    auth.verified_firebase_identity(authorization="Bearer valid-token")
    assert calls["clock_skew_seconds"] == 8


def test_verified_identity_clamps_clock_skew_to_maximum(monkeypatch):
    app = object()
    calls = {}

    def verify_id_token(token, app, check_revoked, clock_skew_seconds=0):
        calls.update(clock_skew_seconds=clock_skew_seconds)
        return {"uid": "test-uid", "email": "student@vrsec.ac.in", "email_verified": True}

    monkeypatch.setenv("HYDROGUARD_FIREBASE_CLOCK_SKEW_SECONDS", "60")
    monkeypatch.setattr(auth, "_firebase_app", lambda: app)
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(auth=SimpleNamespace(verify_id_token=verify_id_token)),
    )

    auth.verified_firebase_identity(authorization="Bearer valid-token")
    assert calls["clock_skew_seconds"] == 10


def test_verified_identity_handles_invalid_or_negative_clock_skew(monkeypatch):
    assert auth._get_clock_skew_seconds() == 5

    monkeypatch.setenv("HYDROGUARD_FIREBASE_CLOCK_SKEW_SECONDS", "invalid")
    assert auth._get_clock_skew_seconds() == 5

    monkeypatch.setenv("HYDROGUARD_FIREBASE_CLOCK_SKEW_SECONDS", "-3")
    assert auth._get_clock_skew_seconds() == 0


def test_verified_identity_rejects_timing_error_outside_tolerance(monkeypatch):
    app = object()

    def reject_token(*args, **kwargs):
        raise ValueError("Token used too early, 1792210490 < 1792210510. Check that your computer's clock is set correctly.")

    monkeypatch.setattr(auth, "_firebase_app", lambda: app)
    monkeypatch.setitem(
        sys.modules,
        "firebase_admin",
        SimpleNamespace(auth=SimpleNamespace(verify_id_token=reject_token)),
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.verified_firebase_identity(authorization="Bearer early-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Firebase bearer token is invalid or expired."
