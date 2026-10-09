"""Threshold configuration API endpoints for HydroGuard."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_roles, require_student_or_admin
from app.db.repositories import ThresholdRepository
from app.schemas.thresholds import ThresholdItem, ThresholdListResponse, ThresholdsUpdateRequest
from app.services.alert_service import AlertService

router = APIRouter(tags=["thresholds"])


def _effective_items(db: Session) -> list[ThresholdItem]:
    effective = AlertService.get_effective_thresholds(db)
    stored = {row.parameter.strip().lower(): row for row in ThresholdRepository.get_all(db)}
    items = []
    for parameter in sorted(effective):
        bounds = effective[parameter]
        row = stored.get(parameter)
        items.append(
            ThresholdItem(
                parameter=parameter,
                min=bounds.get("min"),
                max=bounds.get("max"),
                updated_at=row.updated_at if row is not None else datetime.now(timezone.utc),
            )
        )
    return items


@router.get("/thresholds", response_model=ThresholdListResponse)
def get_thresholds(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_student_or_admin),
) -> ThresholdListResponse:
    """List the effective alert thresholds for every configured parameter."""
    items = _effective_items(db)
    return ThresholdListResponse(thresholds=items, count=len(items))


@router.patch("/thresholds", response_model=ThresholdListResponse)
def update_thresholds(
    payload: ThresholdsUpdateRequest,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles("ADMIN")),
) -> ThresholdListResponse:
    """Create or replace threshold bounds for the listed parameters (admin only)."""
    for parameter, bounds in payload.thresholds.items():
        normalized = parameter.strip().lower()
        if not normalized:
            raise HTTPException(status_code=422, detail="Threshold parameter names must not be blank.")
        ThresholdRepository.upsert(db, normalized, bounds.min, bounds.max)
    items = _effective_items(db)
    return ThresholdListResponse(thresholds=items, count=len(items))
