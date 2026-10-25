"""Tests for the SQLite-to-PostgreSQL migration utility."""

import os
from pathlib import Path
import tempfile
import pytest

from sqlalchemy import inspect, text

from app.db.database import create_app_engine
from scripts.migrate_sqlite_to_postgres import (
    find_latest_verified_backup,
    run_migration,
    verify_source_integrity,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = BACKEND_ROOT / "data" / "backups"


@pytest.fixture
def verified_source_backup() -> Path:
    """Find the verified pre-migration backup."""
    backup = find_latest_verified_backup(BACKEND_ROOT / "data")
    assert backup is not None, "No backup found in data/backups/"
    assert backup.is_file(), f"Backup is not a file: {backup}"
    return backup


def test_verify_source_integrity(verified_source_backup: Path):
    """Ensure the verified backup passes PRAGMA integrity_check."""
    result = verify_source_integrity(verified_source_backup)
    assert result == [("ok",)], f"Integrity check failed: {result}"


def test_migration_dry_run_leaves_target_empty(verified_source_backup: Path):
    """Ensure dry-run mode validates data but rolls back all changes."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        target_path = Path(tf.name)

    try:
        target_url = f"sqlite:///{target_path}"
        report = run_migration(
            source_sqlite=verified_source_backup,
            target_url=target_url,
            dry_run=True,
            on_existing="refuse",
            reconcile_orphans=True,
        )
        assert report["status"] == "DRY_RUN_PASSED"

        # Verify target tables are empty because transaction rolled back
        engine = create_app_engine(target_url)
        with engine.connect() as conn:
            for table in ("sensor_readings", "forecasts", "alerts", "nodes"):
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                assert cnt == 0, f"Table '{table}' should be empty after dry-run rollback."
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)


def test_migration_execution_preserves_records_and_relationships(verified_source_backup: Path):
    """Ensure real migration preserves all records, IDs, and foreign key relationships."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        target_path = Path(tf.name)

    try:
        target_url = f"sqlite:///{target_path}"
        report = run_migration(
            source_sqlite=verified_source_backup,
            target_url=target_url,
            dry_run=False,
            on_existing="refuse",
            reconcile_orphans=True,
        )
        assert report["status"] == "SUCCESS"

        engine = create_app_engine(target_url)
        with engine.connect() as conn:
            # Check sensor_readings
            sr_cnt = conn.execute(text('SELECT COUNT(*) FROM sensor_readings')).scalar()
            assert sr_cnt == 231, f"Expected 231 sensor readings, got {sr_cnt}"

            # Check forecasts
            fc_cnt = conn.execute(text('SELECT COUNT(*) FROM forecasts')).scalar()
            assert fc_cnt == 67, f"Expected 67 forecasts, got {fc_cnt}"

            # Check model_errors
            me_cnt = conn.execute(text('SELECT COUNT(*) FROM model_errors')).scalar()
            assert me_cnt == 235, f"Expected 235 model errors, got {me_cnt}"

            # Check alerts
            alert_cnt = conn.execute(text('SELECT COUNT(*) FROM alerts')).scalar()
            assert alert_cnt == 23, f"Expected 23 alerts (22 original + 1 reconciled), got {alert_cnt}"

            # Check nodes
            node_cnt = conn.execute(text('SELECT COUNT(*) FROM nodes')).scalar()
            assert node_cnt == 21, f"Expected 21 nodes (3 original + 18 reconciled), got {node_cnt}"

            # Check that foreign key integrity holds: zero orphaned records
            orphaned_readings = conn.execute(
                text('SELECT COUNT(*) FROM sensor_readings sr LEFT JOIN nodes n ON sr.node_id = n.node_id WHERE n.node_id IS NULL')
            ).scalar()
            assert orphaned_readings == 0, "No sensor_readings should be orphaned"

            orphaned_alerts = conn.execute(
                text('SELECT COUNT(*) FROM alerts a LEFT JOIN nodes n ON a.node_id = n.node_id WHERE n.node_id IS NULL')
            ).scalar()
            assert orphaned_alerts == 0, "No alerts should be orphaned"

            orphaned_logs = conn.execute(
                text('SELECT COUNT(*) FROM alert_notification_logs anl LEFT JOIN alerts a ON anl.alert_id = a.id WHERE a.id IS NULL')
            ).scalar()
            assert orphaned_logs == 0, "No alert notification logs should be orphaned"

        engine.dispose()

        # Test on-existing=refuse: running migration again without flag should raise RuntimeError
        with pytest.raises(RuntimeError, match="already contains .* records"):
            run_migration(
                source_sqlite=verified_source_backup,
                target_url=target_url,
                dry_run=False,
                on_existing="refuse",
            )

        # Test on-existing=truncate: running migration with truncate should succeed
        truncate_report = run_migration(
            source_sqlite=verified_source_backup,
            target_url=target_url,
            dry_run=False,
            on_existing="truncate",
            reconcile_orphans=True,
        )
        assert truncate_report["status"] == "SUCCESS"

    finally:
        target_path.unlink(missing_ok=True)


def test_migration_normalizes_postgres_target_url(verified_source_backup: Path):
    """Ensure run_migration normalizes postgres:// URLs to postgresql+psycopg://."""
    from unittest.mock import MagicMock, patch

    with patch("scripts.migrate_sqlite_to_postgres.create_app_engine") as mock_engine:
        mock_engine.return_value.dialect.name = "postgresql"
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.return_value.begin.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.scalar.return_value = 0

        try:
            run_migration(
                source_sqlite=verified_source_backup,
                target_url="postgres://user:pass@host:5432/testdb",
                dry_run=True,
                on_existing="refuse",
            )
        except Exception:
            pass
        mock_engine.assert_called_with("postgresql+psycopg://user:pass@host:5432/testdb")
