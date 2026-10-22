"""Device token management API endpoints for HydroGuard.

Provides registration and unregistration endpoints for Firebase Cloud Messaging (FCM)
device push notification tokens, bound to authenticated user sessions.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import authenticated_principal
from app.db import get_db
from app.db.repositories import DeviceTokenRepository
from app.schemas.devices import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DeviceTestNotificationRequest,
    DeviceTestNotificationResponse,
    DeviceUnregisterRequest,
    DeviceUnregisterResponse,
)

router = APIRouter(tags=["devices"])


@router.post(
    "/devices/register",
    response_model=DeviceRegisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Register FCM device token",
    description="Registers or refreshes an FCM device token associated with the authenticated user and server-verified role.",
)
def register_device_token(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(authenticated_principal),
) -> DeviceRegisterResponse:
    """Register an FCM device token for push notification delivery."""
    user_uid = principal.get("uid")
    if not user_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user UID is missing.",
        )

    # Server derives role directly from the authenticated principal token
    role = str(principal.get("role", "student")).lower()
    if role not in ("admin", "student", "faculty"):
        role = "student"

    token_obj = DeviceTokenRepository.register_token(
        db=db,
        user_uid=user_uid,
        role=role,
        token=payload.token.strip(),
        device_type=payload.device_type.strip(),
    )

    return DeviceRegisterResponse(
        status="registered",
        token=token_obj.token,
        user_uid=token_obj.user_uid,
        role=token_obj.role,
        device_type=token_obj.device_type,
    )


@router.post(
    "/devices/unregister",
    response_model=DeviceUnregisterResponse,
    status_code=status.HTTP_200_OK,
    summary="Unregister FCM device token",
    description="Deactivates an FCM device token (e.g. upon user logout).",
)
def unregister_device_token(
    payload: DeviceUnregisterRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(authenticated_principal),
) -> DeviceUnregisterResponse:
    """Deactivate an FCM device token so no further notifications are delivered to it."""
    deactivated = DeviceTokenRepository.deactivate_token(db, token=payload.token.strip())

    return DeviceUnregisterResponse(
        status="unregistered",
        token=payload.token.strip(),
        deactivated=deactivated,
    )


@router.post(
    "/devices/test-notification",
    response_model=DeviceTestNotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch authorized test push notification",
    description="Sends a test push notification to registered devices for mobile alert verification without creating fake sensor readings.",
)
def dispatch_test_notification(
    payload: DeviceTestNotificationRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(authenticated_principal),
) -> DeviceTestNotificationResponse:
    """Send an authorized test notification to verified device tokens."""
    from app.services.push_notification_service import PushNotificationService

    target_uid = payload.user_uid or principal.get("uid")
    if not target_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User UID could not be determined.",
        )

    # Fetch active tokens for this user
    token_records = DeviceTokenRepository.get_tokens_by_user(db, target_uid)
    active_tokens = [t.token for t in token_records if t.is_active]

    if not active_tokens:
        # Also check all active tokens if user is admin
        role = str(principal.get("role", "student")).lower()
        if role == "admin" and not payload.user_uid:
            active_tokens = DeviceTokenRepository.get_active_tokens(db)

    if not active_tokens:
        return DeviceTestNotificationResponse(
            status="SKIPPED_NO_TOKENS",
            tokens_targeted=0,
            success_count=0,
            failure_count=0,
            error_detail=f"No active registered device tokens found for UID '{target_uid}'.",
        )

    firebase_app = PushNotificationService.get_firebase_app_safely()
    if not firebase_app:
        return DeviceTestNotificationResponse(
            status="SKIPPED_NOT_CONFIGURED",
            tokens_targeted=len(active_tokens),
            success_count=0,
            failure_count=0,
            error_detail="Firebase app credentials are not configured on backend.",
        )

    data_payload = {
        "title": payload.title or "HydroGuard: Push Verification",
        "body": payload.body or "Test notification for mobile push verification.",
        "target_screen": payload.target_screen or "water",
        "node_id": payload.node_id or "node_overhead_a",
        "is_test": "true",
    }
    if payload.alert_id:
        data_payload["alert_id"] = str(payload.alert_id)

    dispatch_result = PushNotificationService._dispatch_multicast(
        db=db,
        app=firebase_app,
        tokens=active_tokens,
        title=payload.title or "HydroGuard: Push Verification",
        body=payload.body or "Test notification for mobile push verification.",
        data=data_payload,
    )

    status_str = "SENT" if dispatch_result["success_count"] > 0 else "FAILED"
    return DeviceTestNotificationResponse(
        status=status_str,
        tokens_targeted=len(active_tokens),
        success_count=dispatch_result["success_count"],
        failure_count=dispatch_result["failure_count"],
        error_detail=dispatch_result.get("error_detail"),
    )
