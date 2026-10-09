"""Fail-closed authentication dependencies for Firebase ID tokens and sensors."""

import hmac
import os
from typing import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.auth_models import HydroGuardUser
from app.db.database import get_db


def _firebase_app():
    project_id = os.getenv("HYDROGUARD_FIREBASE_PROJECT_ID", "").strip()
    if not project_id:
        raise HTTPException(status_code=503, detail="Firebase authentication is not configured.")
    try:
        import firebase_admin
        from firebase_admin import credentials

        try:
            app = firebase_admin.get_app("hydroguard-api")
        except ValueError:
            return firebase_admin.initialize_app(
                credentials.ApplicationDefault(),
                {"projectId": project_id},
                name="hydroguard-api",
            )
        if app.project_id != project_id:
            raise HTTPException(
                status_code=503,
                detail="Firebase authentication is configured for a different project.",
            )
        return app
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Firebase authentication could not initialize.") from exc


def _development_principal(
    token: str | None,
    role: str | None,
    uid: str | None,
) -> dict | None:
    """Validate a debug-only local identity when explicitly enabled by env."""
    environment = os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower()
    if environment not in {"development", "dev", "test"}:
        return None
    if os.getenv("HYDROGUARD_ENABLE_DEV_AUTH", "").lower() != "true":
        return None
    expected = os.getenv("HYDROGUARD_DEV_API_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        return None
    normalized_role = (role or "").upper()
    normalized_uid = (uid or "").strip()
    allowed = {
        "demo.student@hydroguard.local": "STUDENT",
        "demo.admin@hydroguard.local": "ADMIN",
    }
    if allowed.get(normalized_uid) != normalized_role:
        return None
    return {"uid": normalized_uid, "role": normalized_role, "development": True}


def _verified_identity(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A Firebase bearer token is required.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="A Firebase bearer token is required.")
    try:
        from firebase_admin import auth

        identity = auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase bearer token is invalid or expired.") from exc

    uid = str(identity.get("uid", "")).strip()
    email = identity.get("email")
    if not uid or not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=401, detail="The Firebase account does not provide a valid identity.")
    if identity.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Use a verified college Google account to continue.")
    return {**identity, "uid": uid, "email": email.strip().lower()}


def verified_firebase_identity(
    authorization: str | None = Header(default=None),
) -> dict:
    """Verify Firebase identity without requiring a role or account record.

    This dependency is reserved for the narrow account bootstrap endpoint.
    """
    return _verified_identity(authorization)


def _database_principal(identity: dict, db: Session) -> dict:
    account = (
        db.query(HydroGuardUser)
        .filter_by(firebase_uid=identity["uid"])
        .one_or_none()
    )
    if account is None:
        raise HTTPException(status_code=403, detail="This account is not authorized for HydroGuard.")
    if account.email != identity["email"]:
        raise HTTPException(status_code=403, detail="The verified email does not match this HydroGuard account.")
    if account.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="This HydroGuard account is not active.")
    role = str(account.role).strip().upper()
    if role not in {"STUDENT", "ADMIN"}:
        raise HTTPException(status_code=403, detail="This account is not authorized for HydroGuard.")
    return {
        **identity,
        "uid": account.firebase_uid,
        "email": account.email,
        "role": role,
        "name": account.display_name,
    }


def authenticated_principal(
    authorization: str | None = Header(default=None),
    x_hydroguard_development_token: str | None = Header(default=None),
    x_hydroguard_development_role: str | None = Header(default=None),
    x_hydroguard_development_uid: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    local = _development_principal(
        x_hydroguard_development_token,
        x_hydroguard_development_role,
        x_hydroguard_development_uid,
    )
    if local is not None:
        return local
    identity = _verified_identity(authorization)
    return _database_principal(identity, db)


def require_roles(*allowed_roles: str) -> Callable:
    allowed = {role.upper() for role in allowed_roles}

    def dependency(principal: dict = Depends(authenticated_principal)) -> dict:
        role = str(principal.get("role", "")).upper()
        if role not in allowed:
            raise HTTPException(status_code=403, detail="This operation is not permitted for your role.")
        return principal

    return dependency


def require_student_or_admin(principal: dict = Depends(authenticated_principal)) -> dict:
    # Roles resolved from the persistent HydroGuard account record are authoritative.
    role = str(principal.get("role", "")).strip().upper()
    if role not in {"STUDENT", "ADMIN"}:
        raise HTTPException(status_code=403, detail="An active STUDENT or ADMIN HydroGuard account is required.")
    return {**principal, "role": role}


def require_sensor_key(x_sensor_token: str | None = Header(default=None)) -> None:
    configured = os.getenv("HYDROGUARD_SENSOR_API_KEY")
    if not configured:
        raise HTTPException(status_code=503, detail="Sensor ingestion authentication is not configured.")
    if not x_sensor_token or not hmac.compare_digest(x_sensor_token, configured):
        raise HTTPException(status_code=401, detail="A valid sensor token is required.")
