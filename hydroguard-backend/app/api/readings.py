from datetime import datetime, timezone

from fastapi import APIRouter, Path

from app.schemas.readings import LatestReadingResponse

router = APIRouter(tags=["readings"])

# Fixed development fixture. Not live hardware. EC and DO stay unset
# until those physical sensors are purchased.
_DEV_TIMESTAMP = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)


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
) -> LatestReadingResponse:
    """Return a historical-or-simulated development reading for the node."""
    return LatestReadingResponse(
        node_id=node_id,
        timestamp=_DEV_TIMESTAMP,
        ph=7.2,
        tds=180.0,
        turbidity=1.2,
        temperature=22.4,
        ec=None,
        do=None,
        flow_rate=18.0,
        source="historical_or_simulated",
    )
