import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.admin_users import router as admin_users_router
from app.api.forecast import router as forecast_router
from app.api.health import router as health_router
from app.api.hostel import router as hostel_router
from app.api.nodes import router as nodes_router
from app.api.readings import router as readings_router
from app.api.research_export import router as research_export_router
from app.api.thresholds import router as thresholds_router
from app.core.auth import FIREBASE_UNAVAILABLE_DETAIL, _firebase_app
from app.db.database import get_db_context, init_db

logging.basicConfig(
    level=os.getenv("HYDROGUARD_LOG_LEVEL", "INFO").strip().upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("hydroguard.startup")

# Local CORS is enabled only in an explicitly non-production environment.
development_environment = os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower()


def _report_firebase_configuration() -> None:
    """Log whether Firebase auth is usable so misconfiguration is visible at boot.

    Registration, login and bootstrap all depend on this. Previously a missing
    service-account key only surfaced as an opaque HTTP 503 on the first sign-in.
    """
    try:
        app = _firebase_app()
    except Exception as exc:
        detail = getattr(exc, "detail", FIREBASE_UNAVAILABLE_DETAIL)
        logger.error(
            "Firebase authentication is NOT usable: %s Sign-in, registration and "
            "account bootstrap will return HTTP 503 until this is fixed.",
            detail,
        )
        return
    logger.info("Firebase authentication ready for project '%s'.", app.project_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create current tables and apply additive SQLite compatibility changes."""
    init_db()
    _report_firebase_configuration()
    if development_environment in {"development", "dev"}:
        from app.db.seed import seed_development_dataset

        with get_db_context() as db:
            seed_development_dataset(db)
    yield


app = FastAPI(
    title="HydroGuard ML API",
    version="1.0.0",
    description=(
        "Backend API for HydroGuard. Responses in this foundation use "
        "historical or simulated development data, not live sensor readings."
    ),
    lifespan=lifespan,
)

local_development_origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=local_development_origins if development_environment in {"development", "dev", "test"} else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(health_router)

app.include_router(readings_router, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")
app.include_router(nodes_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(hostel_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(admin_users_router, prefix="/api/v1")
app.include_router(research_export_router, prefix="/api/v1")
app.include_router(thresholds_router, prefix="/api/v1")
