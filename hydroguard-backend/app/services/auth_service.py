"""Firebase-backed account provisioning and server-owned roles."""

import os

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import _firebase_app
from app.db.auth_models import HydroGuardUser

DEMO_STUDENT_UID = "hydroguard-demo-student"
DEMO_STUDENT_EMAIL = "demo.student@hydroguard.local"
DEMO_ADMIN_UID = "hydroguard-demo-admin"
DEMO_ADMIN_EMAIL = "demo.admin@hydroguard.local"


def development_demo_auth_enabled() -> bool:
    environment = os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower()
    return environment in {"development", "dev", "test"}


def create_development_demo_student_custom_token() -> str:
    """Create a Firebase custom token for the fixed student in explicit dev mode."""
    if not development_demo_auth_enabled():
        # Hide the development-only route when the explicit guard is absent.
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        try:
            firebase_user = firebase_auth.get_user(DEMO_STUDENT_UID, app=app)
        except firebase_auth.UserNotFoundError:
            try:
                firebase_user = firebase_auth.get_user_by_email(DEMO_STUDENT_EMAIL, app=app)
            except firebase_auth.UserNotFoundError:
                firebase_user = firebase_auth.create_user(
                    uid=DEMO_STUDENT_UID,
                    email=DEMO_STUDENT_EMAIL,
                    email_verified=True,
                    display_name="Demo Student",
                    app=app,
                )

        if firebase_user.uid != DEMO_STUDENT_UID or firebase_user.email != DEMO_STUDENT_EMAIL:
            raise HTTPException(status_code=409, detail="The development student identity is already linked elsewhere.")
        if firebase_user.disabled:
            raise HTTPException(status_code=403, detail="The development student account is disabled.")
        if not firebase_user.email_verified or firebase_user.display_name != "Demo Student":
            firebase_user = firebase_auth.update_user(
                firebase_user.uid,
                email_verified=True,
                display_name="Demo Student",
                app=app,
            )

        token = firebase_auth.create_custom_token(firebase_user.uid, app=app)
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Firebase demo authentication is unavailable.",
        ) from exc


def create_development_demo_admin_custom_token() -> str:
    """Create a Firebase custom token for the fixed admin in explicit dev mode."""
    if not development_demo_auth_enabled():
        # Hide the development-only route when the explicit guard is absent.
        raise HTTPException(status_code=404, detail="Not found.")

    try:
        from firebase_admin import auth as firebase_auth

        app = _firebase_app()
        try:
            firebase_user = firebase_auth.get_user(DEMO_ADMIN_UID, app=app)
        except firebase_auth.UserNotFoundError:
            try:
                firebase_user = firebase_auth.get_user_by_email(DEMO_ADMIN_EMAIL, app=app)
            except firebase_auth.UserNotFoundError:
                firebase_user = firebase_auth.create_user(
                    uid=DEMO_ADMIN_UID,
                    email=DEMO_ADMIN_EMAIL,
                    email_verified=True,
                    display_name="Demo Admin",
                    app=app,
                )

        if firebase_user.uid != DEMO_ADMIN_UID or firebase_user.email != DEMO_ADMIN_EMAIL:
            raise HTTPException(status_code=409, detail="The development admin identity is already linked elsewhere.")
        if firebase_user.disabled:
            raise HTTPException(status_code=403, detail="The development admin account is disabled.")
        if not firebase_user.email_verified or firebase_user.display_name != "Demo Admin":
            firebase_user = firebase_auth.update_user(
                firebase_user.uid,
                email_verified=True,
                display_name="Demo Admin",
                app=app,
            )

        token = firebase_auth.create_custom_token(firebase_user.uid, app=app)
        return token.decode("utf-8") if isinstance(token, bytes) else token
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Firebase demo authentication is unavailable.",
        ) from exc


def normalize_email(value: str) -> str:
    return value.strip().lower()


def allowed_student_domains() -> frozenset[str]:
    configured = os.getenv("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "")
    return frozenset(
        domain.strip().lower().lstrip("@")
        for domain in configured.split(",")
        if domain.strip()
    )


def is_approved_student_email(email: str) -> bool:
    normalized = normalize_email(email)
    if normalized == DEMO_STUDENT_EMAIL and development_demo_auth_enabled():
        return True
    if normalized.count("@") != 1:
        return False
    domain = normalized.rsplit("@", 1)[1]
    return domain in allowed_student_domains()


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
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="HydroGuard account permissions could not be synchronized.",
        ) from exc


def revoke_firebase_sessions(uid: str) -> None:
    try:
        from firebase_admin import auth as firebase_auth

        firebase_auth.revoke_refresh_tokens(uid, app=_firebase_app())
    except Exception as exc:
        # Database authorization is checked on every request, so the account
        # remains blocked even if Firebase token revocation is temporarily down.
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


def bootstrap_firebase_user(db: Session, identity: dict) -> HydroGuardUser:
    """Provision or resolve one verified Firebase identity for app access."""
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


def bootstrap_first_admin(db: Session, firebase_user) -> HydroGuardUser:
    """Provision the first ADMIN from a trusted one-time backend CLI."""
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
    sync_firebase_role_claim(uid, "ADMIN")
    return account
