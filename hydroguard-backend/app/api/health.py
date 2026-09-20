from fastapi import APIRouter

from app.schemas.readings import HealthResponse, ModelsLoadedStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return API liveness. Models and sensors are not connected in this step."""
    return HealthResponse(
        status="ok",
        service="HydroGuard ML API",
        version="1.0.0",
        sensors_connected=False,
        models_loaded=ModelsLoadedStatus(
            lstm=False,
            patchtst=False,
            timemixer=False,
        ),
        data_mode="historical_or_simulated",
    )
