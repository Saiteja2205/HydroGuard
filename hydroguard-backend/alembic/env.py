import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models to populate Base.metadata
from app.db.database import Base, create_app_engine, get_masked_database_url, resolve_database_url
from app.db.models import (
    Alert,
    AlertNotificationLog,
    DeviceToken,
    EnsembleWeight,
    Forecast,
    ModelError,
    Node,
    RawTelemetryObservation,
    SensorCalibration,
    SensorReading,
    ThingSpeakMonitorCheckpoint,
    ThresholdConfig,
)
from app.db.auth_models import HydroGuardUser
from app.db import hostel_models

target_metadata = Base.metadata


def get_url() -> str:
    """Resolve target database URL for migrations.

    Supports:
    1. alembic -x db_url=<URL>
    2. config.set_section_option("alembic", "db_url", ...)
    3. config.get_main_option("sqlalchemy.url")
    4. HYDROGUARD_DATABASE_URL
    5. DATABASE_URL
    6. Default project database URL from app.db.database
    """
    x_args = context.get_x_argument(as_dictionary=True)
    override = (
        x_args.get("db_url")
        or config.get_section_option("alembic", "db_url")
        or config.get_main_option("sqlalchemy.url")
    )
    if override and override.strip() and not override.startswith("driver://"):
        url = override.strip()
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    return resolve_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to a live database.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Connects to the database and applies migrations transactionally.
    """
    url = get_url()
    connectable = create_app_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
