"""Database connection and session management for HydroGuard.

Supports both SQLite (for local development and offline testing) and
PostgreSQL (for production cloud deployment, e.g. on Render).
"""

from contextlib import contextmanager
import logging
import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger("hydroguard.database")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = BACKEND_ROOT / "data"
DB_DIR.mkdir(exist_ok=True)


def resolve_database_url() -> str:
    """Resolve and normalize database URL from environment variables.

    Priority:
    1. HYDROGUARD_DATABASE_URL
    2. DATABASE_URL (standard environment variable on Render / Railway / Heroku)
    3. SQLite file specified by HYDROGUARD_DATABASE_PATH
    4. Default local SQLite file at hydroguard-backend/data/hydroguard.db
    """
    raw_url = os.getenv("HYDROGUARD_DATABASE_URL") or os.getenv("DATABASE_URL")
    if raw_url and raw_url.strip():
        url = raw_url.strip()
        # Render / Heroku compatibility: postgres:// or postgresql:// without driver -> postgresql+psycopg://
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    # Default to SQLite file
    db_path = Path(os.getenv("HYDROGUARD_DATABASE_PATH", str(DB_DIR / "hydroguard.db")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


def get_masked_database_url(url: str | None = None) -> str:
    """Return database URL with sensitive credentials masked for safe logging."""
    target_url = url or SQLALCHEMY_DATABASE_URL
    try:
        return make_url(target_url).render_as_string(hide_password=True)
    except Exception:
        # Fallback if make_url cannot parse the string
        if "@" in target_url:
            prefix = target_url.split("://")[0] + "://" if "://" in target_url else ""
            host_part = target_url.split("@")[-1]
            return f"{prefix}***@{host_part}"
        return target_url


def create_app_engine(url: str) -> Engine:
    """Create a configured SQLAlchemy engine appropriate for the URL dialect."""
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 15.0}
        return create_engine(
            url,
            connect_args=connect_args,
            echo=False,
        )

    # PostgreSQL / other production RDBMS
    pool_size = int(os.getenv("HYDROGUARD_DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("HYDROGUARD_DB_MAX_OVERFLOW", "10"))
    pool_recycle = int(os.getenv("HYDROGUARD_DB_POOL_RECYCLE", "1800"))
    pool_timeout = float(os.getenv("HYDROGUARD_DB_POOL_TIMEOUT", "30.0"))

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_timeout=pool_timeout,
        echo=False,
    )


# SQLAlchemy setup
SQLALCHEMY_DATABASE_URL = resolve_database_url()
engine = create_app_engine(SQLALCHEMY_DATABASE_URL)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Configure per-connection SQLite pragmas for concurrency and durability.

    - busy_timeout=5000: Waits up to 5000ms on lock contention before raising OperationalError.
    - synchronous=NORMAL: Durability with minimal fsync overhead in WAL mode.
    Note: PRAGMA journal_mode=WAL is a persistent file property and is configured
    during initialization (init_db) rather than on every connection.
    """
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency injection for database sessions.

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Useful for scripts and background tasks.

    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables and persistence settings.

    Creates all tables if they don't exist and configures WAL journal mode for SQLite.
    """
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL;"))
            connection.commit()

    # Import models here to ensure they are registered with Base
    from app.db.models import (
        Alert,
        AlertNotificationLog,
        DeviceToken,
        Forecast,
        ModelError,
        Node,
        RawTelemetryObservation,
        SensorReading,
        ThingSpeakMonitorCheckpoint,
    )
    from app.db.auth_models import HydroGuardUser
    from app.db import hostel_models
    Base.metadata.create_all(bind=engine)
    ensure_forecast_schema()


def _upgrade_legacy_sqlite_schema() -> None:
    """Add nullable/provenance columns to existing local SQLite installations.

    This is intentionally additive: old EC/DO/flow columns remain in place for
    historical compatibility, but are excluded from all active product APIs.
    """
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "sensor_readings": {
            "red": "INTEGER", "green": "INTEGER", "blue": "INTEGER", "clear": "INTEGER",
            "optical_colour_index": "FLOAT", "calibration_id": "INTEGER",
        },
        "forecasts": {
            "input_start": "DATETIME", "input_end": "DATETIME",
            "horizon_hours": "INTEGER NOT NULL DEFAULT 24",
            "data_source": "VARCHAR(50) NOT NULL DEFAULT 'HISTORICAL_DATA'",
            "model_versions": "JSON", "weight_strategy": "VARCHAR(20) NOT NULL DEFAULT 'initial'",
            "lstm_optical_colour_index": "FLOAT", "patchtst_optical_colour_index": "FLOAT",
            "timemixer_optical_colour_index": "FLOAT", "ensemble_optical_colour_index": "FLOAT",
            "lstm_weight_optical_colour_index": "NUMERIC(5,4) NOT NULL DEFAULT 0.33",
            "patchtst_weight_optical_colour_index": "NUMERIC(5,4) NOT NULL DEFAULT 0.33",
            "timemixer_weight_optical_colour_index": "NUMERIC(5,4) NOT NULL DEFAULT 0.34",
        },
        "model_errors": {
            "actual_timestamp": "DATETIME",
            "evaluated_at": "DATETIME",
            "horizon_hours": "INTEGER NOT NULL DEFAULT 24",
            "data_source": "VARCHAR(50) NOT NULL DEFAULT 'HISTORICAL_DATA'",
            "mape": "NUMERIC(10, 4)",
            "model_version": "VARCHAR(255)",
        },
        "ensemble_weights": {"model_version": "VARCHAR(255)"},
        "emergency_contacts": {"verified": "BOOLEAN NOT NULL DEFAULT 0"},
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))


def ensure_forecast_schema() -> None:
    """Apply supported additive SQLite updates and verify Forecast columns."""
    _upgrade_legacy_sqlite_schema()
    _verify_forecast_schema()


def _verify_forecast_schema() -> None:
    """Verify persisted Forecast columns match the active ORM model.

    SQLite's ``create_all`` intentionally leaves existing tables alone. Keep
    the local additive upgrade above in sync with the ORM and fail during
    initialization, before a request attempts an INSERT, if an older schema
    is missing a column that cannot be safely synthesized.
    """
    if not inspect(engine).has_table("forecasts"):
        raise RuntimeError("Forecast table was not created during database initialization")

    from app.db.models import Forecast

    actual = {column["name"] for column in inspect(engine).get_columns("forecasts")}
    expected = {column.name for column in Forecast.__table__.columns}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(
            "SQLite forecasts schema is behind the SQLAlchemy Forecast model; "
            f"missing columns: {', '.join(missing)}. "
            "Run init_db() to apply supported additive schema updates."
        )


def drop_db() -> None:
    """Drop all database tables.

    WARNING: This will delete all data. Use only for testing.
    """
    Base.metadata.drop_all(bind=engine)


def reset_db() -> None:
    """Reset database by dropping and recreating all tables.

    WARNING: This will delete all data. Use only for testing.
    """
    drop_db()
    init_db()
