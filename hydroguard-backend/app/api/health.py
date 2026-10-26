"""API liveness and separately-triaged dependency checks.

The previous implementation returned a hard-coded ``sensors_connected=False``
plus three hard-coded ``False`` model flags. Those constants were honest only
by accident: they could not distinguish "no hardware attached" from "the
database is down" or "the models never loaded".

This module reports each dependency from evidence gathered at request time:

* ``api``            - the HTTP service answered (implied by this route running)
* ``database``       - a minimal query completed within a bounded timeout
* ``models``         - per-model state read from an already-constructed service
* ``sensor_ingestion`` - a recent REAL_SENSOR heartbeat, or an explicit absence
* ``data_freshness`` - age and provenance of the newest stored observation

Design constraints:

* Health stays public (infrastructure probes need it) and exposes no
  credentials, personal data, stack traces or internal filesystem paths.
* It never loads ML checkpoints, which would turn a liveness probe into a
  multi-second operation.
* Database work is bounded by a configurable timeout, so a slow database
  degrades one field instead of hanging the endpoint.
* Freshness thresholds live in configuration rather than as magic constants.
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.db.models import SensorReading
from app.schemas.readings import (
    DataFreshnessHealth,
    DatabaseHealth,
    HealthResponse,
    ModelHealth,
    ModelsLoadedStatus,
    SensorIngestionHealth,
    serialize_utc_timestamp,
)

logger = logging.getLogger("hydroguard.health")

router = APIRouter(tags=["health"])

SERVICE_NAME = "HydroGuard ML API"
SERVICE_VERSION = "1.0.0"

# Physical-sensor/cloud integration provenance sources.
# Only genuine hardware sources (REAL_SENSOR direct ingestion, THINGSPEAK cloud,
# or ESP32) count toward physical sensor heartbeat.
LIVE_PROVENANCE_SOURCES = ("REAL_SENSOR", "THINGSPEAK", "ESP32")
LIVE_PROVENANCE = "REAL_SENSOR"


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        logger.warning("Ignoring non-numeric %s; using default %s.", name, default)
        return default
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(float(raw)) if raw else default
    except ValueError:
        logger.warning("Ignoring non-numeric %s; using default %s.", name, default)
        return default
    return value if value > 0 else default


DB_TIMEOUT_SECONDS = _positive_float("HYDROGUARD_HEALTH_DB_TIMEOUT_SECONDS", 2.0)
FRESH_SECONDS = _positive_int("HYDROGUARD_HEALTH_FRESH_SECONDS", 900)
SENSOR_HEARTBEAT_SECONDS = _positive_int("HYDROGUARD_HEALTH_SENSOR_HEARTBEAT_SECONDS", 900)

# A single worker keeps probes cheap and prevents unbounded thread growth when
# a database is slow enough to time out repeatedly.
_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hydroguard-health")


def _as_utc(value: datetime) -> datetime:
    """Interpret stored timestamps as UTC (SQLite returns naive datetimes)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_seconds(then: datetime, now: datetime) -> int:
    # Future-dated rows are tolerated by the reading contract's skew window, so
    # clamp rather than reporting a negative age.
    return max(0, int((now - then).total_seconds()))


def _probe_database() -> DatabaseHealth:
    """Run the smallest query SQLite supports. Runs on a worker thread."""
    started = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - exercised by the timeout/degraded tests
        return DatabaseHealth(state="unavailable", detail="The configured database did not answer a minimal query.")
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    return DatabaseHealth(state="ok", latency_ms=latency_ms)


def _database_health(timeout_seconds: float) -> DatabaseHealth:
    """Bounded database check; a slow database degrades instead of hanging."""
    future = _PROBE_EXECUTOR.submit(_probe_database)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return DatabaseHealth(
            state="unavailable",
            detail=f"The database check exceeded the {timeout_seconds:g}s probe budget.",
        )
    except Exception:  # pragma: no cover - defensive
        return DatabaseHealth(state="unavailable", detail="The database check could not be completed.")


def _model_health() -> ModelHealth:
    """Read per-model state without importing or loading anything heavy.

    ``sys.modules`` is inspected instead of importing the forecast module, so
    a cold health probe never pays the cost of importing torch.
    """
    module = sys.modules.get("app.api.forecast")
    service = getattr(module, "forecast_service", None) if module is not None else None
    if service is None:
        return ModelHealth(
            state="not_loaded",
            detail="Forecast checkpoints are loaded lazily on the first forecast request.",
        )

    lstm = getattr(service, "lstm_model", None) is not None
    patchtst = getattr(service, "patchtst_model", None) is not None
    timemixer = getattr(service, "timemixer_model", None) is not None
    state = "loaded" if (lstm or patchtst or timemixer) else "not_loaded"
    detail = None if state == "loaded" else "The forecast service exists but no checkpoint is loaded yet."
    return ModelHealth(state=state, lstm=lstm, patchtst=patchtst, timemixer=timemixer, detail=detail)


def _latest_observation(db: Session) -> tuple[datetime, str] | None:
    row = db.execute(
        select(SensorReading.timestamp, SensorReading.source).order_by(SensorReading.timestamp.desc()).limit(1)
    ).first()
    if row is None:
        return None
    return _as_utc(row[0]), str(row[1])


def _latest_live_observation(db: Session) -> datetime | None:
    row = db.execute(
        select(SensorReading.timestamp)
        .where(SensorReading.source.in_(LIVE_PROVENANCE_SOURCES))
        .order_by(SensorReading.timestamp.desc())
        .limit(1)
    ).first()
    return None if row is None else _as_utc(row[0])


def _sensor_ingestion_health(db: Session, now: datetime) -> SensorIngestionHealth:
    """Report a heartbeat only when LIVE provenance was actually observed."""
    latest = _latest_live_observation(db)
    if latest is None:
        return SensorIngestionHealth(
            state="not_configured",
            detail=(
                "No REAL_SENSOR observation has been ingested. Physical sensor and cloud "
                "integration are not configured, so hardware connectivity is unknown."
            ),
        )
    age = _age_seconds(latest, now)
    state = "recent" if age <= SENSOR_HEARTBEAT_SECONDS else "stale"
    detail = None
    if state == "stale":
        detail = (
            f"The newest REAL_SENSOR observation is {age}s old, outside the "
            f"{SENSOR_HEARTBEAT_SECONDS}s heartbeat window."
        )
    return SensorIngestionHealth(
        state=state,
        last_real_sensor_at=serialize_utc_timestamp(latest),
        age_seconds=age,
        detail=detail,
    )


def _data_freshness_health(db: Session, now: datetime) -> DataFreshnessHealth:
    latest = _latest_observation(db)
    if latest is None:
        return DataFreshnessHealth(state="empty", detail="No observations are stored.")
    when, source = latest
    age = _age_seconds(when, now)
    state = "fresh" if age <= FRESH_SECONDS else "stale"
    detail = None
    if state == "stale":
        detail = f"The newest observation is {age}s old, outside the {FRESH_SECONDS}s freshness window."
    return DataFreshnessHealth(
        state=state,
        latest_observed_at=serialize_utc_timestamp(when),
        age_seconds=age,
        source=source,
        detail=detail,
    )


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    """Return API liveness with independently-derived dependency states.

    A 200 here means only that the HTTP service is answering. Physical sensor
    connectivity is never inferred from the presence of stored rows; it is
    reported separately from LIVE-provenance ingestion evidence.
    """
    now = datetime.now(timezone.utc)
    database = _database_health(DB_TIMEOUT_SECONDS)
    sensor_ingestion = _sensor_ingestion_health(db, now)
    data_freshness = _data_freshness_health(db, now)
    models = _model_health()

    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        # Kept for response compatibility. It is True only when a LIVE
        # observation arrived inside the heartbeat window, never merely
        # because simulated or historical rows exist.
        sensors_connected=sensor_ingestion.state == "recent",
        models_loaded=ModelsLoadedStatus(
            lstm=models.lstm,
            patchtst=models.patchtst,
            timemixer=models.timemixer,
        ),
        # Kept verbatim for response compatibility; provenance for the newest
        # stored row is reported precisely by data_freshness.source above.
        data_mode="historical_or_simulated",
        checked_at=serialize_utc_timestamp(now),
        environment=os.getenv("HYDROGUARD_ENVIRONMENT", "production").strip().lower(),
        database=database,
        models=models,
        sensor_ingestion=sensor_ingestion,
        data_freshness=data_freshness,
    )
