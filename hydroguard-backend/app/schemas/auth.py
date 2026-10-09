"""Contracts for account bootstrap and administrator provisioning."""

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
