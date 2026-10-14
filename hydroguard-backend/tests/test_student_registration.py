"""Registration must reject bad input honestly and never invent a success.

The registration endpoint creates a real, persistent account and mints a
Firebase custom token. A silent failure here is worse than a loud one: it can
either block a legitimate student or (far worse) return HTTP 200 with an empty
token that the Android client would report as a completed sign-in.

These tests pin the contract that Phase 1 fixed and that Phase 3 must not
regress:

* the role is always server-assigned ``STUDENT``; a client cannot smuggle
  ``ADMIN`` through the request body;
* every password complexity condition is enforced server-side, and a password
  is hashed exactly as typed (leading/trailing spaces are legal characters and
  must survive to login);
* unapproved domains, malformed emails, duplicates and invalid bodies fail with
  the correct status code and never mint a token;
* an unavailable authentication provider degrades to an explicit 503 rather
  than a fabricated success.

Isolation: every test scopes itself to unique, obviously-fake email addresses
and deletes only rows it owns. Nothing here touches a real student account or
the development database (``conftest.py`` redirects the engine to a throwaway
SQLite file).
"""

import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.db.auth_models import HydroGuardUser
from app.db.database import get_db_context, init_db
from app.main import app
from app.services import auth_service

# The allowlist is an environment-controlled policy, so every test states the
# domain it expects explicitly rather than inheriting whatever the host has set.
APPROVED_DOMAIN = "vrsec.ac.in"


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


def _remove_user(email):
    """Delete only the row this test owns, so re-runs stay deterministic."""
    with get_db_context() as db:
        rows = (
            db.query(HydroGuardUser)
            .filter(HydroGuardUser.email == email.lower())
            .all()
        )
        for row in rows:
            db.delete(row)
        db.commit()


@pytest.fixture()
def client(monkeypatch):
    init_db()
    _install_fake_firebase(monkeypatch)
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", APPROVED_DOMAIN)
    return TestClient(app)


def _register(client, email, password="Str0ng!Pass", **extra):
    body = {"email": email, "password": password}
    body.update(extra)
    return client.post("/api/v1/auth/student/register", json=body)


# ===== 1. Approved email domain: success and server-side role assignment =====


def test_approved_domain_registers_with_a_server_assigned_student_role(client, monkeypatch):
    issued_claims = _install_fake_firebase(monkeypatch)
    email = f"phase3.approved@{APPROVED_DOMAIN}"
    _remove_user(email)

    response = _register(client, email)

    assert response.status_code == 200, response.text
    body = response.json()
    # The role must come from the server, never from the request body.
    assert body["role"] == "STUDENT"
    assert body["status"] == "ACTIVE"
    assert body["email"] == email
    assert body["token"] == f"custom-token-for-{email}"
    # The minted token must carry the STUDENT claim the Android client trusts.
    assert issued_claims[email]["role"] == "STUDENT"

    with get_db_context() as db:
        account = db.query(HydroGuardUser).filter_by(email=email).one()
        assert account.role == "STUDENT"
        assert account.status == "ACTIVE"
        assert account.password_hash  # a real Argon2id hash, not the plaintext


def test_email_is_normalized_to_lowercase_and_trimmed(client):
    email = f"phase3.mixed.Case@{APPROVED_DOMAIN}"
    _remove_user(email)

    # A stray space and mixed case must both be normalized, not rejected.
    response = _register(client, f"  {email}  ")

    assert response.status_code == 200, response.text
    assert response.json()["email"] == email.lower()
    with get_db_context() as db:
        assert (
            db.query(HydroGuardUser).filter_by(email=email.lower()).count() == 1
        )


# ===== 2. Unapproved email domain =====


def test_unapproved_domain_is_rejected_without_creating_an_account(client):
    email = "phase3.unapproved@not-our-college.edu.in"
    _remove_user(email)

    response = _register(client, email)

    assert response.status_code == 403
    assert "not approved" in response.json()["detail"]
    assert "token" not in response.json()
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


def test_empty_domain_allowlist_rejects_every_student_email(client, monkeypatch):
    """With no configured domains, registration must fail closed."""
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "")
    email = f"phase3.nopolicy@{APPROVED_DOMAIN}"
    _remove_user(email)

    response = _register(client, email)

    assert response.status_code == 403
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


# ===== 3. Empty or malformed email =====


@pytest.mark.parametrize(
    "bad_email",
    [
        "",  # empty
        "not-an-email",  # no @ and no dot
        "user@nodot",  # no dot in the domain
        "a b@vrsec.ac.in",  # whitespace inside the local part
        "@vrsec.ac.in",  # empty local part
        "user@",  # empty domain
        "double@@vrsec.ac.in",  # two @ signs
    ],
)
def test_malformed_emails_are_rejected_with_a_validation_error(client, bad_email):
    response = _register(client, bad_email)
    # Pydantic rejects these before any database or Firebase work happens.
    assert response.status_code == 422, response.text
    assert "token" not in response.json()


# ===== 4. Password complexity: every required condition =====


@pytest.mark.parametrize(
    "bad_password,expected_status",
    [
        # The Pydantic schema enforces min_length=6 before the handler runs, so a
        # short password is a 422; the complexity rules then catch passwords that
        # are long enough but missing a required character class (400).
        ("Ab1!", 422),
        ("abcdef1!", 400),  # no uppercase letter
        ("ABCDEF1!", 400),  # no lowercase letter
        ("Abcdefgh!", 400),  # no digit
        ("Abcdefg11", 400),  # no special character
    ],
)
def test_password_missing_each_complexity_condition_is_rejected(
    client, bad_password, expected_status, request
):
    password = bad_password
    # Deterministic per-parameter email so re-runs always clean the same row.
    email = f"phase3.weak{request.node.callspec.id}@{APPROVED_DOMAIN}".replace(" ", "_")
    _remove_user(email)

    response = _register(client, email, password=password)

    assert response.status_code == expected_status, response.text
    assert "token" not in response.json()
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


def test_a_password_of_only_spaces_is_rejected(client):
    email = f"phase3.spaces@{APPROVED_DOMAIN}"
    _remove_user(email)

    response = _register(client, email, password="      ")

    assert response.status_code == 400
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


# ===== 5. Leading/trailing spaces are legal and must be preserved =====


def test_password_with_leading_and_trailing_spaces_is_preserved_verbatim(client):
    """A password is a secret, not text to be tidied.

    The client deliberately does not trim the password field. If the server
    trimmed it, the account would be created with a password the user never
    typed and every later login attempt would fail for an unexplained reason.
    """
    email = f"phase3.padded@{APPROVED_DOMAIN}"
    padded = "  Str0ng!Pass  "
    _remove_user(email)

    created = _register(client, email, password=padded)
    assert created.status_code == 200, created.text

    # The exact padded secret must sign in...
    assert (
        client.post(
            "/api/v1/auth/student/login",
            json={"email": email, "password": padded},
        ).status_code
        == 200
    )
    # ...and the trimmed value must not, proving nothing was silently stripped.
    rejected = client.post(
        "/api/v1/auth/student/login",
        json={"email": email, "password": "Str0ng!Pass"},
    )
    assert rejected.status_code == 401
    assert rejected.json()["detail"] == "Invalid credentials."


# ===== 6. Duplicate email =====


def test_duplicate_registration_returns_conflict(client):
    email = f"phase3.duplicate@{APPROVED_DOMAIN}"
    _remove_user(email)

    first = _register(client, email)
    assert first.status_code == 200, first.text

    second = _register(client, email)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]
    assert "token" not in second.json()


def test_duplicate_email_is_detected_case_insensitively(client):
    email = f"phase3.caseless@{APPROVED_DOMAIN}"
    _remove_user(email)

    assert _register(client, email).status_code == 200
    # Same address in different case is the same account, not a new one.
    conflicting = _register(client, email.upper())
    assert conflicting.status_code == 409
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email.lower()).count() == 1


# ===== 7. Invalid request body: no client-supplied role =====


def test_extra_fields_are_rejected_so_admin_cannot_be_smuggled(client):
    """``extra="forbid"`` is a security control, not a nicety.

    If the body were lenient, a patched client could post role=ADMIN and the
    server would have to notice and refuse. Forbidding extras rejects the
    request outright, which is the safer failure mode.
    """
    email = f"phase3.privilege@{APPROVED_DOMAIN}"
    _remove_user(email)

    response = client.post(
        "/api/v1/auth/student/register",
        json={
            "email": email,
            "password": "Str0ng!Pass",
            "role": "ADMIN",
            "status": "ACTIVE",
            "id": 1,
        },
    )

    assert response.status_code == 422, response.text
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


@pytest.mark.parametrize(
    "body",
    [
        {"password": "Str0ng!Pass"},  # missing email
        {"email": f"phase3.missing@{APPROVED_DOMAIN}"},  # missing password
        {},  # empty body
        {"email": None, "password": None},  # explicit nulls
    ],
)
def test_missing_or_null_required_fields_are_rejected(client, body):
    response = client.post("/api/v1/auth/student/register", json=body)
    assert response.status_code == 422, response.text
    assert "token" not in response.json()


def test_password_longer_than_the_schema_maximum_is_rejected(client):
    # 128 is the documented maximum; one more must fail closed rather than
    # silently truncate a secret.
    email = f"phase3.toolong@{APPROVED_DOMAIN}"
    _remove_user(email)

    response = _register(client, email, password="Aa1!" * 33)  # 132 chars

    assert response.status_code == 422
    with get_db_context() as db:
        assert db.query(HydroGuardUser).filter_by(email=email).count() == 0


# ===== 8. Authentication provider unavailable =====


def test_unavailable_auth_provider_returns_an_explicit_503(client, monkeypatch):
    """A token-issuance failure must never be reported as a success.

    The account row is committed before Firebase provisioning, so this also
    documents the intended recovery: the response says "the account was created
    but no token was issued, sign in again", and a subsequent login (which
    provisions Firebase itself) succeeds.
    """
    email = f"phase3.fbdown@{APPROVED_DOMAIN}"
    _remove_user(email)

    def _explode():
        raise RuntimeError("firebase_admin is unreachable")

    monkeypatch.setattr(auth_service, "_firebase_app", _explode)

    response = _register(client, email)

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert "could not issue a sign-in token" in detail
    # No fabricated token may escape on a failure.
    assert "token" not in response.json()

    # Recovery: the account exists, so signing in again provisions Firebase and
    # completes. This is exactly what the 503 detail tells the user to do.
    monkeypatch.setattr(auth_service, "_firebase_app", lambda: object())
    recovered = client.post(
        "/api/v1/auth/student/login",
        json={"email": email, "password": "Str0ng!Pass"},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["token"] == f"custom-token-for-{email}"


def test_role_claim_sync_failure_maps_to_a_503_and_is_not_swallowed(client, monkeypatch):
    """A claim that never lands would leave a student unable to reach data.

    This exercises the real ``sync_firebase_role_claim`` error mapping: an
    unexpected provider failure must surface as an explicit 503 rather than
    being swallowed, which would leave the account silently under-privileged.
    """
    from fastapi import HTTPException

    def _explode():
        raise RuntimeError("claims endpoint unavailable")

    monkeypatch.setattr(auth_service, "_firebase_app", _explode)

    with pytest.raises(HTTPException) as raised:
        auth_service.sync_firebase_role_claim("phase3-uid", "STUDENT")

    assert raised.value.status_code == 503
    assert "could not be synchronized" in raised.value.detail


# ===== 9. Sign-in after registration (end to end, no real network) =====


def test_registration_is_immediately_followed_by_a_successful_login(client):
    email = f"phase3.roundtrip@{APPROVED_DOMAIN}"
    _remove_user(email)

    created = _register(client, email, password="Hydro!Guard9")
    assert created.status_code == 200, created.text

    signed_in = client.post(
        "/api/v1/auth/student/login",
        json={"email": email, "password": "Hydro!Guard9"},
    )
    assert signed_in.status_code == 200, signed_in.text
    body = signed_in.json()
    assert body["role"] == "STUDENT"
    assert body["status"] == "ACTIVE"
    assert body["token"]  # never empty on a genuine success


def test_registration_failure_never_returns_a_success_shaped_body(client):
    """Every rejection must look like a rejection to the Android client.

    The client keys off ``token`` being present. A 4xx/5xx carrying a token
    field would send the UI down the success path.
    """
    email = f"phase3.nofalseok@{APPROVED_DOMAIN}"
    _remove_user(email)

    for response in (
        _register(client, f"bad@{APPROVED_DOMAIN}", password="weak"),  # 400
        _register(client, "blocked@evil.example.com"),  # 403
        _register(client, email, password="Str0ng!Pass"),  # 200 first
        _register(client, email, password="Str0ng!Pass"),  # 409 second
    ):
        if response.status_code >= 400:
            body = response.json()
            assert "token" not in body, response.text
            assert "detail" in body, response.text
