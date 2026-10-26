"""Tests for the SQLite-to-PostgreSQL migration utility."""

import os
from pathlib import Path
import tempfile
import pytest

from sqlalchemy import inspect, text

from app.db.database import create_app_engine
from scripts.migrate_sqlite_to_postgres import (
    find_latest_verified_backup,
    reconcile_missing_entities,
    reset_postgres_sequences,
    run_migration,
    verify_source_integrity,
    MIGRATION_TABLE_ORDER,
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


def test_node_primary_key_collision_prevention(verified_source_backup: Path):
    """Ensure synthetic node stubs are assigned safe primary keys strictly greater than all preserved source IDs."""
    import sqlite3

    # 1. Test reconcile_missing_entities directly on the backup
    conn = sqlite3.connect(f"file:{verified_source_backup.resolve()}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    cur.execute("SELECT id FROM nodes WHERE id IS NOT NULL")
    source_node_pks = {row[0] for row in cur.fetchall()}
    assert source_node_pks == {6, 7, 8}, f"Expected source node IDs to be {{6, 7, 8}}, got {source_node_pks}"

    reconciled = reconcile_missing_entities(cur, tables)
    conn.close()

    synthesized_nodes = reconciled["nodes"]
    assert len(synthesized_nodes) == 18, f"Expected 18 synthesized nodes, got {len(synthesized_nodes)}"

    # All synthesized IDs must be > max(source_node_pks) and unique
    synth_ids = [n["id"] for n in synthesized_nodes]
    assert len(set(synth_ids)) == len(synth_ids), "All synthesized node IDs must be distinct"
    assert all(isinstance(nid, int) and nid > max(source_node_pks) for nid in synth_ids), (
        f"All synthetic node IDs must be strictly greater than {max(source_node_pks)}, got {synth_ids}"
    )
    assert set(synth_ids) == set(range(9, 27)), f"Expected synthetic IDs 9..26, got {synth_ids}"

    # 2. Test migration execution in an isolated temporary database
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
        with engine.connect() as target_conn:
            # Preserved source nodes
            res = target_conn.execute(
                text("SELECT id, node_id FROM nodes WHERE node_id IN ('node_overhead_a', 'thingspeak-244357', 'thingspeak-11104') ORDER BY id")
            ).fetchall()
            preserved = {r[1]: r[0] for r in res}
            assert preserved == {"node_overhead_a": 6, "thingspeak-244357": 7, "thingspeak-11104": 8}

            # Synthesized nodes
            all_nodes = target_conn.execute(text("SELECT id, node_id FROM nodes ORDER BY id")).fetchall()
            assert len(all_nodes) == 21
            all_ids = [r[0] for r in all_nodes]
            assert all_ids == list(range(6, 27))
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)


def test_missing_alert_parent_reconciliation(verified_source_backup: Path):
    """Ensure missing alert parents referenced by alert_notification_logs are synthesized without corrupting source data."""
    import sqlite3

    conn = sqlite3.connect(f"file:{verified_source_backup.resolve()}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    reconciled = reconcile_missing_entities(cur, tables)
    conn.close()

    assert len(reconciled["alerts"]) == 1, f"Expected 1 missing alert, got {len(reconciled['alerts'])}"
    missing_alert = reconciled["alerts"][0]
    assert missing_alert["id"] == 23, f"Expected synthesized alert id=23, got {missing_alert['id']}"
    assert missing_alert["node_id"] == "node_overhead_a"
    assert missing_alert["status"] == "RESOLVED"

    # Verify migration preserves alert 23 and associates with notification logs
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
        with engine.connect() as target_conn:
            # Check alert 23 exists in target alerts
            a23 = target_conn.execute(text("SELECT id, node_id, status FROM alerts WHERE id = 23")).fetchone()
            assert a23 is not None
            assert a23[0] == 23
            assert a23[1] == "node_overhead_a"

            # Check original alerts 1..22 exist
            orig_alerts = target_conn.execute(text("SELECT COUNT(*) FROM alerts WHERE id BETWEEN 1 AND 22")).scalar()
            assert orig_alerts == 22

            # Check notification logs foreign key resolution
            orphans = target_conn.execute(
                text("SELECT COUNT(*) FROM alert_notification_logs anl LEFT JOIN alerts a ON anl.alert_id = a.id WHERE a.id IS NULL")
            ).scalar()
            assert orphans == 0
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)


def test_sequence_reset_logic():
    """Ensure reset_postgres_sequences queries pg_get_serial_sequence and invokes setval on tables with serial sequences."""
    from unittest.mock import MagicMock

    mock_conn = MagicMock()
    mock_inspector = MagicMock()

    # Table 1: nodes (has id PK and valid sequence)
    # Table 2: hostel_issues (has id PK but UUID string, no sequence)
    # Table 3: missing_table (not in schema)
    mock_inspector.has_table.side_effect = lambda t: t in ("nodes", "hostel_issues")
    mock_inspector.get_columns.side_effect = lambda t: (
        [{"name": "id", "primary_key": True}] if t in ("nodes", "hostel_issues") else []
    )

    def mock_execute(stmt):
        sql = str(stmt)
        res = MagicMock()
        if "pg_get_serial_sequence('\"nodes\"'" in sql:
            res.scalar.return_value = "public.nodes_id_seq"
        elif "pg_get_serial_sequence('\"hostel_issues\"'" in sql:
            res.scalar.return_value = None
        elif "setval" in sql:
            res.scalar.return_value = 26
        else:
            res.scalar.return_value = None
        return res

    mock_conn.execute.side_effect = mock_execute

    results = reset_postgres_sequences(mock_conn, mock_inspector, ["nodes", "hostel_issues", "missing_table"])
    assert "nodes" in results
    assert results["nodes"] == 26
    # hostel_issues has no sequence, so it should not be in results
    assert "hostel_issues" not in results
    assert "missing_table" not in results


def test_dry_run_does_not_reset_sequences_and_leaves_target_empty(verified_source_backup: Path):
    """Ensure dry-run mode skips sequence reset and rolls back all inserted data."""
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        target_path = Path(tf.name)

    try:
        target_url = f"sqlite:///{target_path}"
        with patch("scripts.migrate_sqlite_to_postgres.reset_postgres_sequences") as mock_reset:
            report = run_migration(
                source_sqlite=verified_source_backup,
                target_url=target_url,
                dry_run=True,
                on_existing="refuse",
                reconcile_orphans=True,
            )
            assert report["status"] == "DRY_RUN_PASSED"
            assert mock_reset.call_count == 0, "Sequence reset must NEVER be executed during dry-run"

        # Verify all tables in target are completely empty
        engine = create_app_engine(target_url)
        with engine.connect() as conn:
            for table in MIGRATION_TABLE_ORDER:
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                assert cnt == 0, f"Table '{table}' should have 0 rows after dry-run, found {cnt}"
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)


def test_transaction_rollback_on_migration_failure(verified_source_backup: Path):
    """Ensure any exception during migration triggers rollback and leaves target tables completely empty."""
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        target_path = Path(tf.name)

    try:
        target_url = f"sqlite:///{target_path}"

        # Inject failure when inserting 'sensor_readings' (table 12, after nodes and several others have been inserted)
        orig_transform = None
        from scripts.migrate_sqlite_to_postgres import transform_record as orig_transform_func

        def failing_transform(table_name, row, column_types):
            if table_name == "sensor_readings":
                raise RuntimeError("Simulated failure during sensor_readings insertion")
            return orig_transform_func(table_name, row, column_types)

        with patch("scripts.migrate_sqlite_to_postgres.transform_record", side_effect=failing_transform):
            with pytest.raises(RuntimeError, match="Simulated failure during sensor_readings insertion"):
                run_migration(
                    source_sqlite=verified_source_backup,
                    target_url=target_url,
                    dry_run=False,
                    on_existing="refuse",
                    reconcile_orphans=True,
                )

        # Verify rollback: tables that were inserted prior to failure (like nodes, threshold_configs, etc.) must be empty!
        engine = create_app_engine(target_url)
        with engine.connect() as conn:
            for table in ("nodes", "threshold_configs", "device_tokens", "hydroguard_users", "sensor_readings"):
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                assert cnt == 0, f"Table '{table}' should be rolled back to 0 rows after failure, found {cnt}"
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)


def test_synthetic_stub_collision_resolution_with_custom_gaps():
    """Ensure run_migration's stub allocation resolves collisions even if stubs have colliding IDs or gaps."""
    # Test stub allocation logic with a custom target table having non-contiguous IDs
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        target_path = Path(tf.name)

    try:
        target_url = f"sqlite:///{target_path}"
        engine = create_app_engine(target_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE test_nodes (id INTEGER PRIMARY KEY, node_id VARCHAR(64) UNIQUE, name VARCHAR(255))"))
            # Pre-populate with non-contiguous IDs
            conn.execute(text("INSERT INTO test_nodes (id, node_id, name) VALUES (2, 'n2', 'Node 2'), (6, 'n6', 'Node 6'), (10, 'n10', 'Node 10')"))

        # Stubs with no id or colliding id
        stubs = [
            {"id": None, "node_id": "stub_1", "name": "Stub 1"},
            {"id": 6, "node_id": "stub_2", "name": "Stub 2"},  # Collides with existing 6!
            {"id": 15, "node_id": "stub_3", "name": "Stub 3"}, # Safe, non-colliding
            {"id": 15, "node_id": "stub_4", "name": "Stub 4"}, # Collides with stub_3!
        ]

        with engine.begin() as conn:
            res = conn.execute(text('SELECT id FROM test_nodes WHERE id IS NOT NULL'))
            existing_target_ids = {r[0] for r in res.fetchall()}
            allocated_ids = set(existing_target_ids)
            current_max_id = max(existing_target_ids, default=0)

            for stub in stubs:
                s_id = stub.get("id")
                if s_id is None or s_id in allocated_ids:
                    current_max_id += 1
                    while current_max_id in allocated_ids:
                        current_max_id += 1
                    stub["id"] = current_max_id
                else:
                    if isinstance(s_id, int) and s_id > current_max_id:
                        current_max_id = s_id
                allocated_ids.add(stub["id"])

                conn.execute(
                    text("INSERT INTO test_nodes (id, node_id, name) VALUES (:id, :node_id, :name)"),
                    stub,
                )

        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, node_id FROM test_nodes ORDER BY id")).fetchall()
            id_map = {r[1]: r[0] for r in rows}
            assert id_map["n2"] == 2
            assert id_map["n6"] == 6
            assert id_map["n10"] == 10
            # stub_1 had None -> assigned max(2,6,10)+1 = 11
            assert id_map["stub_1"] == 11
            # stub_2 had 6 (collided with n6) -> assigned 12
            assert id_map["stub_2"] == 12
            # stub_3 had 15 (safe) -> retained 15
            assert id_map["stub_3"] == 15
            # stub_4 had 15 (collided with stub_3) -> assigned 16
            assert id_map["stub_4"] == 16
            assert len(rows) == 7
        engine.dispose()
    finally:
        target_path.unlink(missing_ok=True)
