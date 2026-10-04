"""Alerts API endpoints for HydroGuard."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_roles
from app.db.repositories import AlertRepository, NodeRepository
from app.schemas.alerts import Alert, AlertCreate, AlertListResponse

router = APIRouter(tags=["alerts"])


@router.get("/nodes/{node_id}/alerts", response_model=AlertListResponse)
def get_alerts(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    status: Optional[str] = Query(None, description="Filter by status (ACTIVE, ACKNOWLEDGED, RESOLVED)"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum number of alerts to return"),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Get alerts for a node."""
    # Ensure node exists
    node = NodeRepository.get_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    alerts = AlertRepository.get_by_node(db, node_id, status=status, limit=limit)
    return AlertListResponse(alerts=alerts, count=len(alerts))


@router.post("/alerts", response_model=Alert)
def create_alert(alert_data: AlertCreate, db: Session = Depends(get_db), principal: dict = Depends(require_roles("ADMIN"))) -> Alert:
    """Create a new alert."""
    # Ensure node exists
    node = NodeRepository.get_by_node_id(db, alert_data.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {alert_data.node_id} not found")

    alert = AlertRepository.create(
        db=db,
        node_id=alert_data.node_id,
        timestamp=datetime.now(timezone.utc),
        parameter=alert_data.parameter,
        value=alert_data.value,
        threshold=alert_data.threshold,
        severity=alert_data.severity,
        message=alert_data.message,
        status="ACTIVE",
    )
    return alert


@router.patch("/alerts/{alert_id}", response_model=Alert)
def update_alert_status(
    alert_id: int = Path(..., ge=1, description="Alert ID"),
    status: str = Query(..., regex="^(ACTIVE|ACKNOWLEDGED|RESOLVED)$", description="New status"),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles("ADMIN")),
) -> Alert:
    """Update alert status."""
    alert = AlertRepository.update_status(db, alert_id, status)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert
