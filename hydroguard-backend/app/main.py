from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.forecast import router as forecast_router
from app.api.health import router as health_router
from app.api.hostel import router as hostel_router
from app.api.nodes import router as nodes_router
from app.api.readings import router as readings_router
from app.api.research_export import router as research_export_router
from app.db.database import init_db

app = FastAPI(
    title="HydroGuard ML API",
    version="1.0.0",
    description=(
        "Backend API for HydroGuard. Responses in this foundation use "
        "historical or simulated development data, not live sensor readings."
    ),
)


@app.on_event("startup")
def initialize_database() -> None:
    """Create current tables and apply additive SQLite compatibility changes."""
    init_db()

# Local development CORS (Android emulator, localhost clients, Swagger UI).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
        "http://10.0.2.2:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(readings_router, prefix="/api/v1")
app.include_router(forecast_router, prefix="/api/v1")
app.include_router(nodes_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(hostel_router, prefix="/api/v1")
app.include_router(research_export_router, prefix="/api/v1")
