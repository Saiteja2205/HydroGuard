"""Pydantic schemas for alert-related API endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Alert record."""

    id: int
    node_id: str
    timestamp: datetime
    parameter: str
    value: float
    threshold: float
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    status: Literal["ACTIVE", "ACKNOWLEDGED", "RESOLVED"]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    """Response for alert list endpoint."""

    alerts: list[Alert]
    count: int


class AlertCreate(BaseModel):
    """Request for creating an alert."""

    node_id: str = Field(..., min_length=1, max_length=64)
    parameter: str = Field(..., min_length=1, max_length=50)
    value: float
    threshold: float
    severity: Literal["INFO", "WARNING", "CRITICAL"] = "WARNING"
    message: str = Field(..., min_length=1, max_length=500)
