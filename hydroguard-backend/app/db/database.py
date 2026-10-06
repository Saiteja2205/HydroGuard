"""Database connection and session management for HydroGuard.

Uses SQLAlchemy with SQLite for local development.
Designed to be easily migrated to PostgreSQL for cloud deployment.
"""

from contextlib import contextmanager
import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database path (SQLite for local development)
# Use absolute path to ensure consistency across different execution contexts
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = BACKEND_ROOT / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = Path(os.getenv("HYDROGUARD_DATABASE_PATH", str(DB_DIR / "hydroguard.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# SQLAlchemy setup
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False,  # Set to True for SQL query logging during development
)

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
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables.

    Creates all tables if they don't exist.
    """
    # Import models here to ensure they are registered with Base
    from app.db.models import Node, SensorReading, Forecast, ModelError, Alert
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
