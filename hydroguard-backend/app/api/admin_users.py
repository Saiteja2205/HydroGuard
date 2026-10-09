"""Admin-only faculty account provisioning and status management."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_roles
from app.db.auth_models import HydroGuardUser
from app.db.database import get_db
from app.schemas.auth import AdminInviteRequest, AdminUserResponse, AdminUserStatusRequest
from app.services.auth_service import revoke_firebase_sessions, sync_firebase_role_claim

router = APIRouter(prefix="/admin/users", tags=["admin-user-management"])


def _response(account: HydroGuardUser) -> AdminUserResponse:
    return AdminUserResponse.model_validate(account)


def _deactivate_firebase_access(uid: str) -> None:
    """Attempt both claim removal and token revocation after DB access is disabled."""
    failures: list[HTTPException] = []
    for operation in (lambda: sync_firebase_role_claim(uid, None), lambda: revoke_firebase_sessions(uid)):
        try:
            operation()
        except HTTPException as exc:
            failures.append(exc)
    if failures:
        raise failures[0]


@router.get("", response_model=list[AdminUserResponse])
def list_admin_users(
    _: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> list[AdminUserResponse]:
    records = (
        db.query(HydroGuardUser)
        .filter(HydroGuardUser.role == "ADMIN")
        .order_by(HydroGuardUser.created_at.asc(), HydroGuardUser.id.asc())
        .all()
    )
    return [_response(account) for account in records]


@router.post("/invite", response_model=AdminUserResponse, status_code=201)
def invite_admin(
    payload: AdminInviteRequest,
    principal: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    account = (
        db.query(HydroGuardUser)
        .filter(HydroGuardUser.email == payload.email)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if account is None:
        account = HydroGuardUser(
            email=payload.email,
            role="ADMIN",
            status="INVITED",
            invited_by_uid=str(principal["uid"]),
        )
        db.add(account)
    else:
        if account.status in {"SUSPENDED", "REVOKED"}:
            raise HTTPException(
                status_code=409,
                detail="This account is inactive. Reactivate it through account management before changing its role.",
            )
        account.role = "ADMIN"
        account.status = "ACTIVE" if account.firebase_uid else "INVITED"
        account.invited_by_uid = str(principal["uid"])
        account.updated_at = now

    db.commit()
    db.refresh(account)
    if account.firebase_uid and account.status == "ACTIVE":
        sync_firebase_role_claim(account.firebase_uid, "ADMIN")
    return _response(account)


@router.patch("/{user_id}", response_model=AdminUserResponse)
def update_admin_status(
    user_id: int,
    payload: AdminUserStatusRequest,
    principal: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    account = db.get(HydroGuardUser, user_id)
    if account is None or account.role != "ADMIN":
        raise HTTPException(status_code=404, detail="Administrator account not found.")

    new_status = payload.status
    if new_status != "ACTIVE" and account.firebase_uid == str(principal.get("uid", "")):
        raise HTTPException(status_code=409, detail="You cannot suspend or revoke your own administrator account.")
    if account.status == "ACTIVE" and new_status != "ACTIVE":
        active_count = (
            db.query(HydroGuardUser)
            .filter_by(role="ADMIN", status="ACTIVE")
            .count()
        )
        if active_count <= 1:
            raise HTTPException(status_code=409, detail="The last active administrator cannot be suspended or revoked.")

    account.status = new_status
    account.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)

    if account.firebase_uid:
        if new_status == "ACTIVE":
            sync_firebase_role_claim(account.firebase_uid, "ADMIN")
        else:
            _deactivate_firebase_access(account.firebase_uid)
    return _response(account)
