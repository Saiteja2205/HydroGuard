"""Tests for Alembic schema migrations."""

import gc
import os
from pathlib import Path
import tempfile
import pytest

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.db.database import create_app_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def test_alembic_upgrade_and_downgrade():
    """Verify Alembic can apply migrations forward and rollback cleanly."""
    tmp_dir = tempfile.mkdtemp(prefix="hydroguard-alembic-")
    test_db_path = Path(tmp_dir) / "test_migration.db"

    try:
        test_url = f"sqlite:///{test_db_path}"
        alembic_cfg = Config(str(ALEMBIC_INI))
        alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", test_url)

        # 1. Upgrade to head
        command.upgrade(alembic_cfg, "head")

        engine = create_app_engine(test_url)
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert "nodes" in tables
            assert "sensor_readings" in tables
            assert "forecasts" in tables
            assert "alerts" in tables
            assert "hydroguard_users" in tables
            assert "hostel_issues" in tables
            assert "alembic_version" in tables

            # Verify key columns exist
            reading_cols = {c["name"] for c in inspector.get_columns("sensor_readings")}
            assert {"ph", "tds", "turbidity", "temperature", "node_id", "timestamp"}.issubset(reading_cols)
        finally:
            engine.dispose()

        # 2. Downgrade to base
        command.downgrade(alembic_cfg, "base")

        engine = create_app_engine(test_url)
        try:
            inspector = inspect(engine)
            downgraded_tables = set(inspector.get_table_names()) - {"alembic_version"}
            assert len(downgraded_tables) == 0, f"Tables still present after downgrade: {downgraded_tables}"
        finally:
            engine.dispose()

    finally:
        gc.collect()
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(f"{test_db_path}{suffix}").unlink(missing_ok=True)
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
