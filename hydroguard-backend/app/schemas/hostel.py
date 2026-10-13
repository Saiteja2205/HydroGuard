"""Validated API contracts for hostel reporting and services."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.storage import STORAGE_KEY_PATTERN

# Path this backend serves its own uploaded photographs from. A reference under
# this prefix is a file the server wrote itself, so unlike an arbitrary URL it
# does not have to be HTTPS to be safe to open.
HOSTEL_PHOTO_PATH_PREFIX = "/api/v1/hostel/lost-found/photos/"

IssueCategory = Literal["Water", "Plumbing", "Electrical", "Room/Furniture", "Cleaning", "Bathroom", "Wi-Fi", "Other"]
# SUBMITTED is the persisted name for an issue that has just been opened by a
# student; the client displays it as "Open". WAITING means the admin is blocked
# on something outside the team (resident, spare part, clarification).
IssueStatus = Literal[
    "SUBMITTED",
    "ACKNOWLEDGED",
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING",
    "RESOLVED",
    "CLOSED",
    "REOPENED",
]


def validate_image_reference(value: str | None) -> str | None:
    """Accept a photograph this server stored, or an external HTTPS URL.

    The first version of this rule rejected every non-HTTPS value because
    uploads were not implemented yet. Now that the backend stores the photo
    itself, its own relative path has to be allowed too — but only the exact
    shape the upload endpoint issues, so a client still cannot smuggle in
    ``http://``, ``file://``, ``//host`` or a traversal in the key.
    """
    if value is None:
        return value
    if value.startswith(HOSTEL_PHOTO_PATH_PREFIX):
        key = value[len(HOSTEL_PHOTO_PATH_PREFIX):]
        if not STORAGE_KEY_PATTERN.fullmatch(key):
            raise ValueError("Uploaded photograph references must use the server-issued storage key.")
        return value
    if value.startswith("https://"):
        return value
    raise ValueError(
        "Image references must be an uploaded HydroGuard photograph or an HTTPS URL."
    )


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueCreate(StrictInput):
    category: IssueCategory
    location: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=5, max_length=5000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"
    image_url: str | None = Field(default=None, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def image_reference(cls, value: str | None) -> str | None:
        return validate_image_reference(value)


class IssueRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    reporter_uid: str
    category: IssueCategory
    location: str
    description: str
    severity: str
    image_url: str | None
    status: IssueStatus
    assigned_uid: str | None
    resolution: str | None
    created_at: datetime
    updated_at: datetime


class IssueStatusChange(StrictInput):
    status: IssueStatus
    comment: str | None = Field(default=None, max_length=2000)
    assigned_uid: str | None = Field(default=None, max_length=128)
    resolution: str | None = Field(default=None, max_length=5000)


class IssueEventRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    issue_id: str
    actor_uid: str
    from_status: str | None
    to_status: str
    comment: str | None
    created_at: datetime


class IssueFeedbackCreate(StrictInput):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class IssueFeedbackRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    issue_id: str
    reporter_uid: str
    stars: int
    comment: str | None
    created_at: datetime


class IssueReopen(StrictInput):
    reason: str = Field(min_length=5, max_length=2000)


class NoticeCreate(StrictInput):
    title: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=2, max_length=10000)
    category: Literal["GENERAL", "MAINTENANCE", "WATER", "EMERGENCY", "EVENT"]
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"
    expires_at: datetime | None = None


class NoticeRecord(NoticeCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    author_uid: str
    created_at: datetime


class EmergencyContactCreate(StrictInput):
    category: Literal["WARDEN", "SECURITY"]
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=4, max_length=40, pattern=r"^\+?[0-9][0-9 ()-]{2,38}$")
    details: str | None = Field(default=None, max_length=500)
    active: bool = True
    verified: bool = False


class EmergencyContactRecord(EmergencyContactCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    updated_by: str
    updated_at: datetime


class LostFoundCreate(StrictInput):
    kind: Literal["LOST", "FOUND"]
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=5, max_length=5000)
    category: Literal["ID", "Keys", "Phone", "Wallet", "Books", "Bag", "Electronics", "Other"]
    image_url: str | None = Field(default=None, max_length=2048)
    location: str = Field(min_length=2, max_length=255)
    item_date: datetime

    @field_validator("image_url")
    @classmethod
    def image_reference(cls, value: str | None) -> str | None:
        return validate_image_reference(value)


class LostFoundRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: str
    reporter_uid: str
    kind: str
    title: str
    description: str
    category: str
    image_url: str | None
    location: str
    item_date: datetime
    moderation_status: str
    created_at: datetime


class LostFoundModeration(StrictInput):
    moderation_status: Literal["APPROVED", "REJECTED", "REMOVED"]


class LostFoundPhotoUpload(BaseModel):
    """Returned by the upload endpoint: the reference to attach to an item."""

    model_config = ConfigDict(extra="forbid")

    image_url: str


class HostelFeedbackCreate(StrictInput):
    category: Literal["Water", "Cleanliness", "Maintenance", "Wi-Fi", "Common Areas", "Overall Hostel Experience"]
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=3000)


class HostelFeedbackRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    reporter_uid: str
    category: str
    rating: int
    comment: str | None
    created_at: datetime
