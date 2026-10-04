"""Pydantic schemas for node-related API endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Node(BaseModel):
    """Node record."""

    id: int
    node_id: str
    name: str
    location: str
    status: Literal["online", "offline", "maintenance"]
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NodeCreate(BaseModel):
    """Request for creating a node."""

    node_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    location: str = Field(..., min_length=1, max_length=255)
    status: Literal["online", "offline", "maintenance"] = "offline"


class NodeListResponse(BaseModel):
    """Response for node list endpoint."""

    nodes: list[Node]
    count: int
