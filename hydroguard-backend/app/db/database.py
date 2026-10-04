"""Database connection and session management for HydroGuard.

Uses SQLAlchemy with SQLite for local development.
Designed to be easily migrated to PostgreSQL for cloud deployment.
"""

from contextlib import contextmanager
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
DB_PATH = DB_DIR / "hydroguard.db"

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
    _upgrade_legacy_sqlite_schema()


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
        },
        "model_errors": {
            "actual_timestamp": "DATETIME",
            "evaluated_at": "DATETIME",
            "horizon_hours": "INTEGER NOT NULL DEFAULT 24",
            "data_source": "VARCHAR(50) NOT NULL DEFAULT 'HISTORICAL_DATA'",
            "mape": "NUMERIC(10, 4)",
        },
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
