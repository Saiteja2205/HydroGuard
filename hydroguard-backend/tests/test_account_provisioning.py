"""Server-side user provisioning, role source-of-truth, and admin management tests."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import admin_users
from app.api import auth as auth_api
from app.core import auth
from app.db.auth_models import HydroGuardUser
from app.schemas.auth import AdminInviteRequest, AdminUserStatusRequest
from app.services import auth_service


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    HydroGuardUser.__table__.create(bind=engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def synced_roles(monkeypatch):
    updates = []
    monkeypatch.setattr(
        auth_service,
        "sync_firebase_role_claim",
        lambda uid, role: updates.append((uid, role)),
    )
    return updates


def identity(uid: str, email: str, *, verified: bool = True, **extra) -> dict:
    return {
        "uid": uid,
        "email": email,
        "email_verified": verified,
        "name": "HydroGuard Test User",
        **extra,
    }


def test_new_approved_domain_user_bootstraps_as_student_without_role_claim(db, monkeypatch, synced_roles):
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in,siddhartha.edu.in")

    account = auth_service.bootstrap_firebase_user(
        db,
        identity("student-1", "new.batch.user@vrsec.ac.in"),
    )

    assert (account.role, account.status, account.firebase_uid) == ("STUDENT", "ACTIVE", "student-1")
    assert synced_roles == [("student-1", "STUDENT")]


def test_bootstrap_endpoint_accepts_identity_without_token_role_claim(db, monkeypatch, synced_roles):
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")
    identity_claims = identity("student-1", "first.login@vrsec.ac.in")

    response = auth_api.bootstrap_account(identity=identity_claims, db=db)

    assert response.role == "STUDENT"
    assert response.status == "ACTIVE"
    assert synced_roles == [("student-1", "STUDENT")]


def test_existing_student_remains_student_after_domain_config_changes(db, monkeypatch, synced_roles):
    db.add(HydroGuardUser(
        firebase_uid="student-1",
        email="existing@old-college.edu",
        role="STUDENT",
        status="ACTIVE",
    ))
    db.commit()
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "new-college.edu")

    account = auth_service.bootstrap_firebase_user(
        db,
        identity("student-1", "existing@old-college.edu"),
    )

    assert account.role == "STUDENT"
    assert synced_roles == [("student-1", "STUDENT")]


def test_existing_admin_remains_admin(db, monkeypatch, synced_roles):
    db.add(HydroGuardUser(
        firebase_uid="admin-1",
        email="faculty@not-student-domain.example",
        role="ADMIN",
        status="ACTIVE",
    ))
    db.commit()
    monkeypatch.delenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", raising=False)

    account = auth_service.bootstrap_firebase_user(
        db,
        identity("admin-1", "faculty@not-student-domain.example"),
    )

    assert account.role == "ADMIN"
    assert synced_roles == [("admin-1", "ADMIN")]


def test_unapproved_domain_is_rejected_without_creating_record(db, monkeypatch, synced_roles):
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

    with pytest.raises(HTTPException) as error:
        auth_service.bootstrap_firebase_user(db, identity("unknown-1", "person@other.edu"))

    assert error.value.status_code == 403
    assert db.query(HydroGuardUser).count() == 0
    assert synced_roles == []


def test_unverified_email_is_rejected(db, monkeypatch, synced_roles):
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

    with pytest.raises(HTTPException) as error:
        auth_service.bootstrap_firebase_user(
            db,
            identity("student-1", "student@vrsec.ac.in", verified=False),
        )

    assert error.value.status_code == 403
    assert db.query(HydroGuardUser).count() == 0
    assert synced_roles == []


@pytest.mark.parametrize(
    ("role", "status"),
    [("STUDENT", "SUSPENDED"), ("ADMIN", "SUSPENDED"), ("ADMIN", "REVOKED")],
)
def test_inactive_accounts_are_rejected(db, monkeypatch, synced_roles, role, status):
    email = f"{role.lower()}@vrsec.ac.in"
    db.add(HydroGuardUser(
        firebase_uid="blocked-1",
        email=email,
        role=role,
        status=status,
    ))
    db.commit()
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

    with pytest.raises(HTTPException) as error:
        auth_service.bootstrap_firebase_user(db, identity("blocked-1", email))

    assert error.value.status_code == 403
    assert synced_roles == []


def test_invited_admin_is_bound_by_verified_email_then_becomes_active(db, synced_roles):
    inviter = {"uid": "admin-1", "role": "ADMIN"}
    invite = admin_users.invite_admin(
        AdminInviteRequest(email="new.faculty@external.example"),
        principal=inviter,
        db=db,
    )
    assert invite.role == "ADMIN"
    assert invite.status == "INVITED"

    account = auth_service.bootstrap_firebase_user(
        db,
        identity("faculty-2", "new.faculty@external.example", role="STUDENT"),
    )

    assert account.role == "ADMIN"
    assert account.status == "ACTIVE"
    assert account.firebase_uid == "faculty-2"
    assert synced_roles == [("faculty-2", "ADMIN")]


def test_admin_table_has_no_small_admin_count_limit(db):
    db.add_all([
        HydroGuardUser(
            firebase_uid=f"faculty-{index}",
            email=f"faculty{index}@college.example",
            display_name=f"Faculty {index}",
            role="ADMIN",
            status="ACTIVE",
        )
        for index in range(12)
    ])
    db.commit()

    records = admin_users.list_admin_users(_={"uid": "faculty-0", "role": "ADMIN"}, db=db)

    assert len(records) == 12
    assert all(record.role == "ADMIN" for record in records)


def test_student_cannot_use_admin_dependency_and_cannot_send_role_in_invite(db):
    admin_dependency = auth.require_roles("ADMIN")
    with pytest.raises(HTTPException) as error:
        admin_dependency(principal={"uid": "student-1", "role": "STUDENT"})
    assert error.value.status_code == 403

    with pytest.raises(ValidationError):
        AdminInviteRequest.model_validate({"email": "faculty@college.example", "role": "ADMIN"})


def test_last_active_admin_cannot_revoke_self(db):
    db.add(HydroGuardUser(
        firebase_uid="admin-1",
        email="admin@college.example",
        role="ADMIN",
        status="ACTIVE",
    ))
    db.commit()
    account = db.query(HydroGuardUser).one()

    with pytest.raises(HTTPException) as error:
        admin_users.update_admin_status(
            account.id,
            AdminUserStatusRequest(status="REVOKED"),
            principal={"uid": "admin-1", "role": "ADMIN"},
            db=db,
        )

    assert error.value.status_code == 409
    assert account.status == "ACTIVE"


def test_admin_can_promote_existing_student_and_suspend_then_reactivate_or_revoke(db, monkeypatch):
    updates = []
    revoked = []
    monkeypatch.setattr(admin_users, "sync_firebase_role_claim", lambda uid, role: updates.append((uid, role)))
    monkeypatch.setattr(admin_users, "revoke_firebase_sessions", lambda uid: revoked.append(uid))
    db.add_all([
        HydroGuardUser(firebase_uid="admin-1", email="admin@college.example", role="ADMIN", status="ACTIVE"),
        HydroGuardUser(firebase_uid="staff-2", email="staff@college.example", role="STUDENT", status="ACTIVE"),
    ])
    db.commit()
    admin = {"uid": "admin-1", "role": "ADMIN"}

    promoted = admin_users.invite_admin(
        AdminInviteRequest(email="staff@college.example"),
        principal=admin,
        db=db,
    )
    assert promoted.role == "ADMIN"
    assert promoted.status == "ACTIVE"
    assert updates == [("staff-2", "ADMIN")]

    target = db.query(HydroGuardUser).filter_by(firebase_uid="staff-2").one()
    suspended = admin_users.update_admin_status(
        target.id,
        AdminUserStatusRequest(status="SUSPENDED"),
        principal=admin,
        db=db,
    )
    assert suspended.status == "SUSPENDED"
    assert updates[-1] == ("staff-2", None)
    assert revoked == ["staff-2"]
    with pytest.raises(HTTPException) as blocked:
        auth._database_principal(identity("staff-2", "staff@college.example"), db)
    assert blocked.value.status_code == 403

    active = admin_users.update_admin_status(
        target.id,
        AdminUserStatusRequest(status="ACTIVE"),
        principal=admin,
        db=db,
    )
    assert active.status == "ACTIVE"
    assert updates[-1] == ("staff-2", "ADMIN")

    revoked_record = admin_users.update_admin_status(
        target.id,
        AdminUserStatusRequest(status="REVOKED"),
        principal=admin,
        db=db,
    )
    assert revoked_record.status == "REVOKED"
    with pytest.raises(HTTPException) as blocked:
        auth._database_principal(identity("staff-2", "staff@college.example"), db)
    assert blocked.value.status_code == 403


def test_deactivation_attempts_token_revocation_when_claim_removal_fails(db, monkeypatch):
    calls = []

    def fail_claim_removal(uid, role):
        calls.append(("claim", uid, role))
        raise HTTPException(status_code=503, detail="claim sync unavailable")

    monkeypatch.setattr(admin_users, "sync_firebase_role_claim", fail_claim_removal)
    monkeypatch.setattr(
        admin_users,
        "revoke_firebase_sessions",
        lambda uid: calls.append(("revoke", uid)),
    )

    with pytest.raises(HTTPException) as error:
        admin_users._deactivate_firebase_access("target-uid")

    assert error.value.status_code == 503
    assert calls == [("claim", "target-uid", None), ("revoke", "target-uid")]


def test_invite_does_not_reactivate_inactive_admin_implicitly(db):
    db.add(HydroGuardUser(
        firebase_uid="suspended-admin",
        email="suspended@college.example",
        role="ADMIN",
        status="SUSPENDED",
    ))
    db.commit()

    with pytest.raises(HTTPException) as error:
        admin_users.invite_admin(
            AdminInviteRequest(email="suspended@college.example"),
            principal={"uid": "active-admin", "role": "ADMIN"},
            db=db,
        )

    assert error.value.status_code == 409
    assert db.query(HydroGuardUser).filter_by(firebase_uid="suspended-admin").one().status == "SUSPENDED"


def test_bootstrap_first_admin_is_explicit_and_repeatable_for_same_account(db, synced_roles):
    first = SimpleNamespace(
        uid="first-admin",
        email="first@college.example",
        email_verified=True,
        display_name="First Admin",
        custom_claims=None,
    )

    account = auth_service.bootstrap_first_admin(db, first)
    repeated = auth_service.bootstrap_first_admin(db, first)

    assert account.role == "ADMIN"
    assert repeated.firebase_uid == "first-admin"
    assert db.query(HydroGuardUser).count() == 1
    assert synced_roles == [("first-admin", "ADMIN"), ("first-admin", "ADMIN")]

    other = SimpleNamespace(
        uid="second-admin",
        email="second@college.example",
        email_verified=True,
        display_name="Second Admin",
        custom_claims=None,
    )
    with pytest.raises(RuntimeError, match="already exists"):
        auth_service.bootstrap_first_admin(db, other)


def test_existing_firebase_user_without_hydroguard_record_follows_domain_policy(db, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")
    monkeypatch.setattr(auth_service, "sync_firebase_role_claim", lambda uid, role: None)

    allowed = auth_service.bootstrap_firebase_user(
        db,
        identity("new-firebase-user", "different.username@vrsec.ac.in"),
    )
    assert allowed.role == "STUDENT"

    with pytest.raises(HTTPException) as error:
        auth_service.bootstrap_firebase_user(
            db,
            identity("other-firebase-user", "person@unapproved.example"),
        )
    assert error.value.status_code == 403
