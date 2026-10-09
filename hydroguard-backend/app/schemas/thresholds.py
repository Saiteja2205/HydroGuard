"""Pydantic schemas for the configurable alert-threshold endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ThresholdRange(BaseModel):
    """One bound pair for a parameter; at least one bound is required."""

    min: Optional[float] = Field(None, ge=-10000, le=10000)
    max: Optional[float] = Field(None, ge=-10000, le=10000)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ThresholdRange":
        if self.min is None and self.max is None:
            raise ValueError("At least one of min or max must be provided.")
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("min must be lower than max.")
        return self


class ThresholdItem(BaseModel):
    """Stored threshold for a single parameter."""

    parameter: str
    min: Optional[float]
    max: Optional[float]
    updated_at: datetime


class ThresholdListResponse(BaseModel):
    """Response for GET /thresholds."""

    thresholds: list[ThresholdItem]
    count: int


class ThresholdsUpdateRequest(BaseModel):
    """Request for PATCH /thresholds; replaces the bounds of each listed parameter."""

    thresholds: dict[str, ThresholdRange] = Field(..., min_length=1, max_length=20)
