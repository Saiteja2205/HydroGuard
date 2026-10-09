"""Firebase identity bootstrap endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import verified_firebase_identity
from app.db.database import get_db
from app.db.auth_models import HydroGuardUser
from app.schemas.auth import AuthenticatedUserResponse, DevelopmentSessionResponse
from app.services.auth_service import (
    bootstrap_firebase_user,
    create_development_demo_student_custom_token,
    create_development_demo_admin_custom_token,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/bootstrap", response_model=AuthenticatedUserResponse)
def bootstrap_account(
    identity: dict = Depends(verified_firebase_identity),
    db: Session = Depends(get_db),
) -> AuthenticatedUserResponse:
    account: HydroGuardUser = bootstrap_firebase_user(db, identity)
    return AuthenticatedUserResponse(
        uid=account.firebase_uid,
        email=account.email,
        display_name=account.display_name or account.email.split("@", 1)[0],
        role=account.role,
        status="ACTIVE",
    )


@router.post("/development/demo-student-session", response_model=DevelopmentSessionResponse)
def create_demo_student_session() -> DevelopmentSessionResponse:
    """Issue a Firebase custom credential for the fixed, low-privilege dev student."""
    return DevelopmentSessionResponse(
        custom_token=create_development_demo_student_custom_token(),
    )


@router.post("/development/demo-admin-session", response_model=DevelopmentSessionResponse)
def create_demo_admin_session() -> DevelopmentSessionResponse:
    """Issue a Firebase custom credential for the fixed, dev admin."""
    return DevelopmentSessionResponse(
        custom_token=create_development_demo_admin_custom_token(),
    )

