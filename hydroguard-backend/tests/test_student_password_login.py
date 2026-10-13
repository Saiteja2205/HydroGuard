"""College-email registration and login return a usable Firebase custom token."""

import sys
import types

from fastapi.testclient import TestClient

from app.db.auth_models import HydroGuardUser, hash_password
from app.db.database import get_db_context, init_db
from app.main import app
from app.services import auth_service


def _install_fake_firebase(monkeypatch):
    """Replace firebase_admin so token issuance works without real credentials."""
    fake = types.ModuleType("firebase_admin")
    issued_claims = {}

    class _Users:
        @staticmethod
        def get_user(uid, app=None):
            return types.SimpleNamespace(uid=uid, custom_claims=None)

        @staticmethod
        def create_user(**kwargs):
            return types.SimpleNamespace(uid=kwargs["uid"], custom_claims=None)

        @staticmethod
        def create_custom_token(uid, developer_claims=None, app=None):
            # Mirrors the real firebase_admin signature (developer_claims, not
            # claims) so a mismatched production call raises TypeError here.
            issued_claims[uid] = dict(developer_claims or {})
            return f"custom-token-for-{uid}".encode("utf-8")

        @staticmethod
        def set_custom_user_claims(uid, claims, app=None):
            issued_claims[uid] = dict(claims or {})

    fake.auth = _Users
    monkeypatch.setitem(sys.modules, "firebase_admin", fake)
    monkeypatch.setattr(auth_service, "_firebase_app", lambda: object())
    return issued_claims


def test_student_login_returns_the_firebase_custom_token(monkeypatch):
    init_db()
    issued_claims = _install_fake_firebase(monkeypatch)

    email = "login.token.student@vrsec.ac.in"
    with get_db_context() as db:
        if db.query(HydroGuardUser).filter_by(email=email).one_or_none() is None:
            db.add(HydroGuardUser(
                firebase_uid=None,
                email=email,
                display_name="Token Student",
                role="STUDENT",
                status="ACTIVE",
                password_hash=hash_password("Str0ng!Pass"),
            ))
            db.commit()

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/student/login",
        json={"email": email, "password": "Str0ng!Pass"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token"] == f"custom-token-for-{email}"
    assert body["role"] == "STUDENT"
    assert body["status"] == "ACTIVE"
    assert body["email"] == email
    assert issued_claims[email]["role"] == "STUDENT"


def test_student_login_rejects_a_wrong_password_without_leaking_details(monkeypatch):
    init_db()
    _install_fake_firebase(monkeypatch)

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/student/login",
        json={"email": "missing.student@vrsec.ac.in", "password": "Str0ng!Pass"},
    )

    assert response.status_code == 401
    assert "Invalid credentials." in response.json()["detail"]
    assert "token" not in response.json()


def test_student_registration_accepts_an_empty_full_name(monkeypatch):
    """The Android form has no name field, so an empty name must still register."""
    init_db()
    _install_fake_firebase(monkeypatch)
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

    client = TestClient(app)
    for email in ("register.student@vrsec.ac.in", "second.student@vrsec.ac.in"):
        with get_db_context() as db:
            existing = db.query(HydroGuardUser).filter_by(email=email).one_or_none()
            if existing is not None:
                db.delete(existing)
                db.commit()

    # Empty string (what the app sends) and an omitted field must both work.
    response = client.post(
        "/api/v1/auth/student/register",
        json={"full_name": "", "email": "register.student@vrsec.ac.in", "password": "Str0ng!Pass"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["display_name"] == "register.student"
    assert body["role"] == "STUDENT"
    assert body["token"] == "custom-token-for-register.student@vrsec.ac.in"

    omitted = client.post(
        "/api/v1/auth/student/register",
        json={"email": "second.student@vrsec.ac.in", "password": "Str0ng!Pass"},
    )
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["display_name"] == "second.student"


def test_student_registration_rejects_an_unapproved_college_domain(monkeypatch):
    init_db()
    _install_fake_firebase(monkeypatch)
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/student/register",
        json={"email": "someone@other-college.edu.in", "password": "Str0ng!Pass"},
    )

    assert response.status_code == 403
    assert "not approved" in response.json()["detail"]
