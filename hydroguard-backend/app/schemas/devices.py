"""Pydantic schemas for device registration and push notification tokens."""

from typing import Optional
from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    """Payload to register an FCM device token."""

    token: str = Field(..., min_length=10, max_length=512, description="FCM device registration token")
    device_type: str = Field(default="android", max_length=32, description="Client device type (e.g. android)")


class DeviceRegisterResponse(BaseModel):
    """Response confirming device token registration."""

    status: str = "registered"
    token: str
    user_uid: str
    role: str
    device_type: str


class DeviceUnregisterRequest(BaseModel):
    """Payload to unregister/deactivate an FCM device token."""

    token: str = Field(..., min_length=10, max_length=512, description="FCM device registration token")


class DeviceUnregisterResponse(BaseModel):
    """Response confirming device token unregistration."""

    status: str = "unregistered"
    token: str
    deactivated: bool


class DeviceTestNotificationRequest(BaseModel):
    """Payload to trigger an authorized test notification to a device."""

    title: Optional[str] = "HydroGuard: Push Verification"
    body: Optional[str] = "Test notification for mobile push verification."
    target_screen: Optional[str] = "water"
    alert_id: Optional[str] = None
    node_id: Optional[str] = "node_overhead_a"
    user_uid: Optional[str] = None  # None targets calling principal's tokens


class DeviceTestNotificationResponse(BaseModel):
    """Response confirming push notification dispatch status."""

    status: str
    tokens_targeted: int
    success_count: int
    failure_count: int
    error_detail: Optional[str] = None
