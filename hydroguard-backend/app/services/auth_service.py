"""Firebase-backed account provisioning, student registration, and password authentication.

Student registration is restricted to approved college email domains.
Passwords are hashed with Argon2id (fallback SHA-256 if argon2 unavailable).
Login verifies the hash and issues a Firebase custom token tied to the
persistent HydroGuard user record.
"""

import logging
import os
import re
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import _firebase_app, _development_principal
from app.db.auth_models import HydroGuardUser, hash_password, verify_password
from app.db.database import get_db_context

logger = logging.getLogger("hydroguard.auth")

DEMO_STUDENT_UID = "hydroguard-demo-student"
DEMO_STUDENT_EMAIL = "demo.student@hydroguard.local"
DEMO_ADMIN_UID = "hydroguard-demo-admin"
DEMO_ADMIN_EMAIL = "demo.admin@hydroguard.local"


def create_development_demo_student_custom_token() -> str:
    """Create a Firebase custom token for the fixed student in explicit dev mode."""
    if not development_demo_auth_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        try:
            firebase_user = firebase_auth.get_user(DEMO_STUDENT_UID, app=app)
        except Exception:
            firebase_user = firebase_auth.create_user(
                uid=DEMO_STUDENT_UID,
                email=DEMO_STUDENT_EMAIL,
                email_verified=True,
                display_name="Demo Student",
                app=app,
            )
        token = firebase_auth.create_custom_token(firebase_user.uid, app=app)
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Firebase demo authentication is unavailable.") from exc


def create_development_demo_admin_custom_token() -> str:
    """Create a Firebase custom token for the fixed admin in explicit dev mode."""
    if not development_demo_auth_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        try:
            firebase_user = firebase_auth.get_user(DEMO_ADMIN_UID, app=app)
        except Exception:
            firebase_user = firebase_auth.create_user(
                uid=DEMO_ADMIN_UID,
                email=DEMO_ADMIN_EMAIL,
                email_verified=True,
                display_name="Demo Admin",
                app=app,
            )
        token = firebase_auth.create_custom_token(firebase_user.uid, app=app)
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Firebase demo authentication is unavailable.") from exc


# Original bootstrap_firebase_user — kept identical so existing tests and callers
# continue to work without modification. This function is defined at module level
# so that it can be referenced by name without triggering a circular import.
def _bootstrap_firebase_user_original(db: Session, identity: dict) -> HydroGuardUser:
    """Original implementation of ``bootstrap_firebase_user``.

    Kept here by name so that ``from app.services.auth_service import
    bootstrap_firebase_user`` works for test compatibility.
    """
    uid = str(identity.get("uid", "")).strip()
    email_value = identity.get("email")
    email = normalize_email(email_value) if isinstance(email_value, str) else ""
    if not uid or not email or identity.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Use a verified college Google account to continue.")
    if email == DEMO_STUDENT_EMAIL and not development_demo_auth_enabled():
        raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")
    if email == DEMO_ADMIN_EMAIL and not development_demo_auth_enabled():
        raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")

    account = _find_account(db, uid, email)
    display_name = identity.get("name") or identity.get("display_name")
    display_name = display_name.strip() if isinstance(display_name, str) else ""

    if account is None:
        if email == DEMO_ADMIN_EMAIL:
            if not development_demo_auth_enabled():
                raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")
            account = HydroGuardUser(
                firebase_uid=uid,
                email=email,
                display_name=display_name or "Demo Administrator",
                role="ADMIN",
                status="ACTIVE",
            )
            db.add(account)
        else:
            if not is_approved_student_email(email):
                raise HTTPException(status_code=403, detail="This college account is not eligible for HydroGuard.")
            account = HydroGuardUser(
                firebase_uid=uid,
                email=email,
                display_name=display_name or email.split("@", 1)[0],
                role="STUDENT",
                status="ACTIVE",
            )
            db.add(account)
    else:
        if account.email != email:
            raise HTTPException(status_code=403, detail="The verified email does not match this HydroGuard account.")
        if account.firebase_uid not in (None, uid):
            raise HTTPException(status_code=403, detail="This email is linked to a different Firebase account.")
        if account.role not in {"STUDENT", "ADMIN"}:
            raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")
        if email == DEMO_STUDENT_EMAIL and account.role != "STUDENT":
            raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")
        if email == DEMO_ADMIN_EMAIL:
            if not development_demo_auth_enabled():
                raise HTTPException(status_code=403, detail="This account is not eligible for HydroGuard.")
            if account.role != "ADMIN":
                account.role = "ADMIN"
            account.status = "ACTIVE"
        if account.status == "INVITED" and account.role == "ADMIN":
            account.status = "ACTIVE"
            account.firebase_uid = uid
        elif account.status != "ACTIVE":
            raise HTTPException(status_code=403, detail="This HydroGuard account is not active.")
        elif account.firebase_uid is None:
            account.firebase_uid = uid
        if display_name:
            account.display_name = display_name

    try:
        db.commit()
        db.refresh(account)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This account could not be linked safely. Contact a HydroGuard administrator.") from exc

    sync_firebase_role_claim(account.firebase_uid, account.role)
    return account


# Bind the name that tests and other modules expect.
bootstrap_firebase_user = _bootstrap_firebase_user_original


def development_demo_auth_enabled() -> bool:
    environment = os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower()
    return environment in {"development", "dev", "test"}


def bootstrap_first_admin(db: Session, firebase_user) -> HydroGuardUser:
    """Provision the first ADMIN from a trusted one-time backend CLI."""
    STUDENT_DOMAIN_ALLOWLIST = load_allowlist()

    email = normalize_email(firebase_user.email or "")
    uid = str(firebase_user.uid or "").strip()
    if not uid or not email or firebase_user.email_verified is not True:
        raise RuntimeError("The Firebase account must have a verified email address.")

    current_admin = (
        db.query(HydroGuardUser)
        .filter_by(role="ADMIN", status="ACTIVE")
        .order_by(HydroGuardUser.id.asc())
        .first()
    )
    if current_admin is not None and current_admin.firebase_uid != uid:
        raise RuntimeError("An active HydroGuard administrator already exists.")

    account = _find_account(db, uid, email)
    if account is not None and account.email != email:
        raise RuntimeError("The Firebase UID is already linked to a different email.")
    if account is not None and account.firebase_uid not in (None, uid):
        raise RuntimeError("The email is already linked to a different Firebase UID.")

    if account is None:
        account = HydroGuardUser(
            firebase_uid=uid,
            email=email,
            role="ADMIN",
            status="ACTIVE",
            display_name=(firebase_user.display_name or email.split("@", 1)[0]),
        )
        db.add(account)
    else:
        account.firebase_uid = uid
        account.role = "ADMIN"
        account.status = "ACTIVE"
        account.display_name = firebase_user.display_name or account.display_name

    db.commit()
    db.refresh(account)
    sync_firebase_role_claim(account.firebase_uid, "ADMIN")
    return account


def normalize_email(value: str) -> str:
    return value.strip().lower()


def load_allowlist() -> frozenset[str]:
    """Load the approved student email domains from the environment."""
    configured = os.getenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "")
    return frozenset(
        domain.strip().lower().lstrip("@")
        for domain in configured.split(",")
        if domain.strip()
    )


def allowed_student_domains() -> frozenset[str]:
    """Return the approved student email domains frozenset."""
    return load_allowlist()


def is_approved_student_email(email: str) -> bool:
    """Check if an email domain is in the approved student allowlist."""
    normalized = normalize_email(email)
    if normalized == DEMO_STUDENT_EMAIL and development_demo_auth_enabled():
        return True
    if normalized.count("@") != 1:
        return False
    domain = normalized.rsplit("@", 1)[1]
    return domain in load_allowlist()


def sync_firebase_role_claim(uid: str, role: str | None) -> None:
    """Synchronize a custom role claim without discarding other custom claims."""
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        firebase_user = firebase_auth.get_user(uid, app=app)
        claims = dict(firebase_user.custom_claims or {})
        if role is None:
            claims.pop("role", None)
        else:
            claims["role"] = role
        firebase_auth.set_custom_user_claims(uid, claims or None, app=app)
    except HTTPException:
        # Already logged and mapped by _firebase_app(); do not mask it.
        raise
    except Exception as exc:
        logger.error(
            "Role claim synchronization failed for uid=%s role=%s (%s: %s)",
            uid,
            role,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="HydroGuard account permissions could not be synchronized.",
        ) from exc


def revoke_firebase_sessions(uid: str) -> None:
    try:
        from firebase_admin import auth as firebase_auth

        firebase_auth.revoke_refresh_tokens(uid, app=_firebase_app())
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Session revocation failed for uid=%s (%s: %s)",
            uid,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Firebase sessions could not be revoked. The account remains blocked by HydroGuard.",
        ) from exc


def _find_account(db: Session, uid: str, email: str) -> HydroGuardUser | None:
    by_uid = db.query(HydroGuardUser).filter_by(firebase_uid=uid).one_or_none()
    by_email = (
        db.query(HydroGuardUser)
        .filter(func.lower(HydroGuardUser.email) == email)
        .one_or_none()
    )
    if by_uid is not None and by_email is not None and by_uid.id != by_email.id:
        raise HTTPException(status_code=409, detail="This account identity is already linked to another HydroGuard user.")
    return by_uid or by_email


def is_password_valid(plain_text: str, hash_value: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    return verify_password(plain_text, hash_value)


def create_access_token(uid: str, role: str, expires_delta: int = 3600) -> str:
    """Create a Firebase custom access token for the given user UID and role."""
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        # The firebase_admin Python SDK names this parameter developer_claims;
        # passing claims= raises TypeError and the token is never issued.
        token = firebase_auth.create_custom_token(uid, developer_claims={"role": role}, app=app)
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not create authentication token.") from exc


def validate_password_complexity(password: str) -> bool:
    """Minimum password requirements.

    - At least 6 characters
    - At least one lowercase letter
    - At least one uppercase letter
    - At least one digit
    - At least one special character (non-alphanumeric)
    """
    if len(password) < 6:
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[^a-zA-Z0-9]", password):
        return False
    return True


def register_student(
    db: Session,
    full_name: str,
    email: str,
    password: str,
) -> tuple[HydroGuardUser, str]:
    """Register a new student account.

    - Normalizes the email and validates the domain against the approved list.
    - Rejects ``ADMIN`` role requests.
    - Hashes the password with Argon2id.
    - Creates a persistent ``HydroGuardUser`` record with role ``STUDENT``.
    - Provisions a Firebase custom token linked to the account.

    Returns:
        A tuple of the created user record and the Firebase custom token. The
        token is empty only when Firebase provisioning failed, in which case the
        client reports that sign-in could not be completed.

    Raises:
        HTTPException: If the email domain is not approved, the password does not
            meet complexity requirements, the email is a duplicate, or any other
            validation failure occurs.
    """
    STUDENT_DOMAIN_ALLOWLIST = load_allowlist()

    normalized_email = normalize_email(email)

    # Validate password complexity
    if not validate_password_complexity(password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters and contain at least one "
            "lowercase letter, one uppercase letter, one digit, and one special "
            "character.",
        )

    # Validate email domain
    if not is_approved_student_email(normalized_email):
        approved = sorted(load_allowlist())
        raise HTTPException(
            status_code=403,
            detail="College email domain not approved. Approved domains are: "
            f"{', '.join(approved)}.",
        )

    # Check for duplicate email
    existing = (
        db.query(HydroGuardUser)
        .filter(func.lower(HydroGuardUser.email) == normalized_email)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="A HydroGuard account already exists with this email address.",
        )

    # Hash the password
    password_hash = hash_password(password)

    # Create the student account
    account = HydroGuardUser(
        firebase_uid=None,
        email=normalized_email,
        display_name=full_name or normalized_email.split("@", 1)[0],
        role="STUDENT",
        status="ACTIVE",
        password_hash=password_hash,
    )
    db.add(account)

    try:
        db.commit()
        db.refresh(account)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This account could not be saved safely. Contact a HydroGuard administrator.",
        ) from exc

    # Provision Firebase user and create custom token
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        try:
            firebase_user = firebase_auth.get_user(normalized_email, app=app)
        except Exception:
            firebase_user = firebase_auth.create_user(
                uid=normalized_email,
                email=normalized_email,
                display_name=account.display_name,
                email_verified=True,
                app=app,
            )
        account.firebase_uid = firebase_user.uid
        db.commit()

        # Create custom token tied to the student account with role claim
        token = firebase_auth.create_custom_token(
            firebase_user.uid, developer_claims={"role": "STUDENT"}, app=app
        )
        access_token = token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        # _firebase_app() already logged why; never report success without a token.
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Student registration could not issue a token for %s (%s: %s)",
            normalized_email,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="The account was created but HydroGuard could not issue a sign-in "
            "token. Sign in again, or contact your administrator if the problem persists.",
        ) from exc

    # Synchronize role claim
    sync_firebase_role_claim(account.firebase_uid, "STUDENT")

    return account, access_token


def login_student(
    db: Session,
    email: str,
    password: str,
) -> tuple[HydroGuardUser, str]:
    """Authenticate a student user and issue a Firebase custom token.

    - Normalizes the email.
    - Looks up the persistent ``HydroGuardUser`` record.
    - Verifies the password hash using Argon2id.
    - If valid, creates/provisions a Firebase user and returns a custom token.
    - If invalid, raises ``HTTPException`` with a generic error to avoid leaking
      whether the email exists or the password is wrong.

    Returns:
        A tuple of the ``HydroGuardUser`` record and the Firebase custom token.

    Raises:
        HTTPException: If the email is not found, the password is incorrect, or
            the account is disabled.
    """
    normalized_email = normalize_email(email)

    account = (
        db.query(HydroGuardUser)
        .filter(func.lower(HydroGuardUser.email) == normalized_email)
        .one_or_none()
    )

    if account is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    if account.password_hash is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Verify password hash
    if not is_password_valid(password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    # Account is valid; ensure Firebase user exists
    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()

        # Provision or retrieve the Firebase user
        try:
            firebase_user = firebase_auth.get_user(
                account.firebase_uid or normalized_email, app=app
            )
        except Exception:
            firebase_user = firebase_auth.create_user(
                uid=account.firebase_uid or normalized_email,
                email=normalized_email,
                display_name=account.display_name,
                email_verified=True,
                app=app,
            )

        # Issue custom token with role claim
        token = firebase_auth.create_custom_token(
            firebase_user.uid, developer_claims={"role": account.role}, app=app
        )
        access_token = token.decode("utf-8") if isinstance(token, bytes) else token

    except HTTPException:
        # Configuration failure already logged by _firebase_app(); keep its detail.
        raise
    except Exception as exc:
        # Keep the generic client-facing message but record the real cause
        # server-side. Never log the password, the token, or key material.
        logger.error(
            "Token issuance failed for %s (%s: %s)",
            normalized_email,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503, detail="Authentication service unavailable."
        ) from exc

    return account, access_token


def development_login(role: str) -> dict:
    """Process a development-only debug login.

    This is the existing flow for ``STUDENT`` or ``ADMIN`` in debug builds,
    using the fixed demo identities from ``.dev-auth.env``.
    """
    if not development_demo_auth_enabled():
        return {"status": "disabled", "message": "Development login is not enabled."}

    if role.upper() == "ADMIN":
        return create_development_demo_admin_custom_token()
    elif role.upper() == "STUDENT":
        return create_development_demo_student_custom_token()
    else:
        return {"status": "error", "message": f"Unsupported role: {role}"}