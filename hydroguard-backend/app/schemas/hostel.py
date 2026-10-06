"""Validated API contracts for hostel reporting and services."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IssueCategory = Literal["Water", "Plumbing", "Electrical", "Room/Furniture", "Cleaning", "Bathroom", "Wi-Fi", "Other"]
IssueStatus = Literal["SUBMITTED", "ACKNOWLEDGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED"]


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
    def images_must_use_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Image references must use HTTPS. Direct uploads are not configured yet.")
        return value


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
    category: Literal["WARDEN", "SECURITY", "COLLEGE_EMERGENCY", "AMBULANCE", "FIRE"]
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
    def images_must_use_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("Image references must use HTTPS. Direct uploads are not configured yet.")
        return value


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


class EventCreate(StrictInput):
    name: str = Field(min_length=2, max_length=180)
    starts_at: datetime
    location: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=5000)
    organizer: str = Field(min_length=2, max_length=120)


class EventRecord(EventCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    author_uid: str
    created_at: datetime


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
