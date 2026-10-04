from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import require_sensor_key
from app.db.repositories import NodeRepository, SensorReadingRepository
from app.schemas.readings import (
    HistoryResponse,
    LatestReadingResponse,
    ReadingCreate,
    ReadingResponse,
)

router = APIRouter(tags=["readings"])

# Fixed development fixture. It is explicitly labelled DEMO and is never a
# real-time sensor observation.
_DEV_TIMESTAMP = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


def _product_source(source: str) -> str:
    """Normalize previously stored lowercase provenance tags during migration."""
    value = source.strip().upper()
    return {
        "ESP32": "REAL_SENSOR",
        "MANUAL": "HISTORICAL_DATA",
        "HISTORICAL_DEMO": "DEMO",
        "HISTORICAL_OR_SIMULATED": "DEMO",
    }.get(value, value)


@router.get(
    "/nodes/{node_id}/readings/latest",
    response_model=LatestReadingResponse,
)
def get_latest_reading(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier, e.g. node_overhead_a",
    ),
    db: Session = Depends(get_db),
) -> LatestReadingResponse:
    """Return the latest reading for a node from database, or fallback to fixture."""
    # Try to get from database first
    reading = SensorReadingRepository.get_latest_by_node(db, node_id)

    if reading:
        return LatestReadingResponse(
            node_id=reading.node_id,
            timestamp=reading.timestamp,
            ph=float(reading.ph),
            tds=float(reading.tds),
            turbidity=float(reading.turbidity),
            temperature=float(reading.temperature) if reading.temperature is not None else None,
            red=reading.red,
            green=reading.green,
            blue=reading.blue,
            clear=reading.clear,
            optical_colour_index=reading.optical_colour_index,
            calibration_id=reading.calibration_id,
            source=_product_source(reading.source),
        )

    # Fallback to development fixture if no data in database
    return LatestReadingResponse(
        node_id=node_id,
        timestamp=_DEV_TIMESTAMP,
        ph=7.2,
        tds=180.0,
        turbidity=1.2,
        temperature=22.4,
        red=None,
        green=None,
        blue=None,
        clear=None,
        optical_colour_index=None,
        source="DEMO",
    )


@router.post("/readings", response_model=ReadingResponse)
def create_reading(reading_data: ReadingCreate, db: Session = Depends(get_db), _: None = Depends(require_sensor_key)) -> ReadingResponse:
    """Insert a sensor reading into the database."""
    # Ensure node exists (create if not)
    node = NodeRepository.get_or_create(
        db=db,
        node_id=reading_data.node_id,
        name=f"Node {reading_data.node_id}",
        location="Unknown",
        status="offline",
    )

    reading = SensorReadingRepository.create(
        db=db,
        node_id=reading_data.node_id,
        timestamp=reading_data.timestamp,
        ph=reading_data.ph,
        tds=reading_data.tds,
        turbidity=reading_data.turbidity,
        temperature=reading_data.temperature,
        red=reading_data.red,
        green=reading_data.green,
        blue=reading_data.blue,
        clear=reading_data.clear,
        optical_colour_index=reading_data.optical_colour_index,
        calibration_id=reading_data.calibration_id,
        source=reading_data.source,
    )
    from app.services.error_tracking import ErrorTrackingService
    ErrorTrackingService.evaluate_actual_reading(db, reading)
    return reading


@router.get("/nodes/{node_id}/readings/history", response_model=HistoryResponse)
def get_reading_history(
    node_id: str = Path(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Node identifier",
    ),
    start: Optional[datetime] = Query(None, description="Start timestamp (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="End timestamp (ISO 8601)"),
    limit: Optional[int] = Query(None, ge=1, le=10000, description="Maximum number of readings"),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    """Get historical readings for a node."""
    # Ensure node exists
    node = NodeRepository.get_by_node_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    readings = SensorReadingRepository.get_history_by_node(db, node_id, start=start, end=end, limit=limit)
    return HistoryResponse(readings=readings, count=len(readings))
