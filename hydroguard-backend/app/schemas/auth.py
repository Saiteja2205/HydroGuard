"""Contracts for account bootstrap, student registration, and administrator provisioning."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_and_validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid faculty email address.")
        return normalized


class AdminUserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ACTIVE", "SUSPENDED", "REVOKED"]


class AuthenticatedUserResponse(BaseModel):
    uid: str
    email: str
    display_name: str
    role: Literal["STUDENT", "ADMIN"]
    status: Literal["ACTIVE"]


class DevelopmentSessionResponse(BaseModel):
    custom_token: str


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    email: str
    display_name: str | None
    role: Literal["ADMIN"]
    status: Literal["INVITED", "ACTIVE", "SUSPENDED", "REVOKED"]
    created_at: datetime
    updated_at: datetime


class StudentRegisterRequest(BaseModel):
    """Request model for student registration.

    - Full name and college email are required.
    - Password must meet complexity requirements (enforced server-side).
    - Email domain must be in the approved allowlist (`HYDROGUARD_ALLOWED_STUDENT_DOMAINS`).
    """
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(default="", max_length=200)

    email: str = Field(min_length=5, max_length=320)

    password: str = Field(min_length=6, max_length=128)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        # The Android form has no name field yet; an empty value is allowed and the
        # account display name is then derived from the college email address.
        return (value or "").strip()

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid college email address.")
        return normalized


class StudentLoginRequest(BaseModel):
    """Request model for student password login.

    - Email and password are validated server-side.
    - No role may be supplied by the client.
    """
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=320)

    password: str = Field(min_length=6, max_length=128)


class LoginResponse(BaseModel):
    """Response returned after successful student registration or login.

    - ``token`` is the Firebase custom token the Android client exchanges for a
      session. It is empty only when the backend could not provision Firebase,
      in which case sign-in fails with an explicit error on the client.
    """
    model_config = ConfigDict(extra="forbid")

    uid: str
    email: str
    display_name: str
    role: Literal["STUDENT"]
    status: Literal["ACTIVE"]
    token: str = ""
