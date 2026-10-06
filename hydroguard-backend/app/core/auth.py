"""Fail-closed authentication dependencies for Firebase ID tokens and sensors."""

import hmac
import os
from typing import Callable

from fastapi import Depends, Header, HTTPException


def _firebase_app():
    project_id = os.getenv("HYDROGUARD_FIREBASE_PROJECT_ID")
    if not project_id:
        raise HTTPException(status_code=503, detail="Firebase authentication is not configured.")
    try:
        import firebase_admin
        from firebase_admin import credentials

        try:
            return firebase_admin.get_app("hydroguard-api")
        except ValueError:
            return firebase_admin.initialize_app(
                credentials.ApplicationDefault(),
                {"projectId": project_id},
                name="hydroguard-api",
            )
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


def authenticated_principal(
    authorization: str | None = Header(default=None),
    x_hydroguard_development_token: str | None = Header(default=None),
    x_hydroguard_development_role: str | None = Header(default=None),
    x_hydroguard_development_uid: str | None = Header(default=None),
) -> dict:
    local = _development_principal(
        x_hydroguard_development_token,
        x_hydroguard_development_role,
        x_hydroguard_development_uid,
    )
    if local is not None:
        return local
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A Firebase bearer token is required.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="A Firebase bearer token is required.")
    try:
        from firebase_admin import auth

        return auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase bearer token is invalid or expired.") from exc


def require_roles(*allowed_roles: str) -> Callable:
    allowed = {role.upper() for role in allowed_roles}

    def dependency(principal: dict = Depends(authenticated_principal)) -> dict:
        role = str(principal.get("role", "")).upper()
        if role not in allowed:
            raise HTTPException(status_code=403, detail="This operation is not permitted for your role.")
        return principal

    return dependency


def require_student_or_admin(principal: dict = Depends(authenticated_principal)) -> dict:
    # An authenticated Firebase account without a custom role claim is a
    # student. ADMIN is granted only through a server-managed custom claim.
    role = str(principal.get("role", "STUDENT")).upper()
    if role not in {"STUDENT", "ADMIN"}:
        raise HTTPException(status_code=403, detail="A STUDENT or ADMIN role claim is required.")
    return principal


def require_sensor_key(x_sensor_token: str | None = Header(default=None)) -> None:
    configured = os.getenv("HYDROGUARD_SENSOR_API_KEY")
    if not configured:
        raise HTTPException(status_code=503, detail="Sensor ingestion authentication is not configured.")
    if not x_sensor_token or not hmac.compare_digest(x_sensor_token, configured):
        raise HTTPException(status_code=401, detail="A valid sensor token is required.")
