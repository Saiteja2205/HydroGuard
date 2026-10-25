#!/usr/bin/env python3
"""HydroGuard — Safe, Transactional SQLite-to-PostgreSQL Data Migration Utility.

Transfers persisted records from a verified SQLite backup to an initialized PostgreSQL
(or other SQLAlchemy-supported) database while preserving IDs, timestamps, relationships,
and sequences.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.database import (
    Base,
    create_app_engine,
    get_masked_database_url,
    resolve_database_url,
)
from app.db import models
from app.db import auth_models
from app.db import hostel_models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hydroguard.migration")

# Explicit dependency order for data insertion
MIGRATION_TABLE_ORDER = [
    # Tier 1 (Root independent tables)
    "nodes",
    "threshold_configs",
    "thingspeak_monitor_checkpoints",
    "device_tokens",
    "hydroguard_users",
    "emergency_contacts",
    "hostel_notices",
    "hostel_feedback",
    "lost_found_items",
    "hostel_issues",
    # Tier 2 (Dependencies on Tier 1)
    "sensor_calibrations",
    "sensor_readings",
    "forecasts",
    "ensemble_weights",
    "alerts",
    "issue_events",
    "issue_feedback",
    # Tier 3 (Dependencies on Tier 2)
    "model_errors",
    "alert_notification_logs",
    "raw_telemetry_observations",
]


def find_latest_verified_backup(data_dir: Path) -> Optional[Path]:
    """Find the newest verified backup in the backups directory."""
    backups_dir = data_dir / "backups"
    if not backups_dir.exists():
        return None
    candidates = list(backups_dir.glob("hydroguard_backup_*.db")) + list(backups_dir.glob("*.db"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def parse_datetime(val: Any) -> Optional[datetime]:
    """Parse SQLite timestamp string or return datetime."""
    if val is None or isinstance(val, datetime):
        return val
    if not isinstance(val, str):
        return None
    val_str = val.strip()
    if not val_str:
        return None
    try:
        # ISO format
        if "T" in val_str or "+" in val_str or val_str.endswith("Z"):
            clean = val_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
        else:
            dt = datetime.fromisoformat(val_str)
        return dt
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
    logger.warning("Could not parse datetime string: %r; preserving as None", val)
    return None


def transform_record(table_name: str, row: Dict[str, Any], column_types: Dict[str, Any]) -> Dict[str, Any]:
    """Transform record values from SQLite format to target ORM/dialect types."""
    transformed = {}
    for col, val in row.items():
        if col not in column_types:
            continue
        col_type = column_types[col]
        type_str = str(col_type).upper()

        if val is None:
            transformed[col] = None
        elif "DATETIME" in type_str or "TIMESTAMP" in type_str:
            transformed[col] = parse_datetime(val)
        elif "BOOLEAN" in type_str:
            transformed[col] = bool(val)
        elif "JSON" in type_str:
            if isinstance(val, str):
                try:
                    transformed[col] = json.loads(val)
                except Exception:
                    transformed[col] = val
            else:
                transformed[col] = val
        else:
            transformed[col] = val
    return transformed


def verify_source_integrity(source_path: Path) -> List[Tuple[Any, ...]]:
    """Open source SQLite database in read-only mode and verify integrity."""
    if not source_path.is_file():
        raise FileNotFoundError(f"Source SQLite file does not exist: {source_path}")

    uri = f"file:{source_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        result = cur.fetchall()
        return result
    finally:
        conn.close()


def reconcile_missing_entities(
    src_cur: sqlite3.Cursor,
    source_tables: Set[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Identify foreign keys in SQLite that reference missing parent records.

    Because SQLite has foreign keys disabled by default, older test/seed records
    may point to non-existent parents (e.g. historical contract nodes or deleted alerts).
    Returns synthesized parent records needed to satisfy relational constraints in PostgreSQL.
    """
    reconciliation: Dict[str, List[Dict[str, Any]]] = {
        "nodes": [],
        "alerts": [],
    }

    # 1. Discover all node_ids across tables that reference nodes
    existing_nodes: Set[str] = set()
    if "nodes" in source_tables:
        src_cur.execute("SELECT node_id FROM nodes")
        existing_nodes = {row[0] for row in src_cur.fetchall()}

    referenced_nodes: Set[str] = set()
    for tbl in ("sensor_readings", "forecasts", "ensemble_weights", "alerts", "model_errors", "sensor_calibrations"):
        if tbl in source_tables:
            src_cur.execute(f'SELECT DISTINCT node_id FROM "{tbl}" WHERE node_id IS NOT NULL')
            referenced_nodes.update(row[0] for row in src_cur.fetchall())

    missing_nodes = referenced_nodes - existing_nodes
    if missing_nodes:
        logger.info("Found %d referenced node_ids missing from 'nodes' table.", len(missing_nodes))
        now_dt = datetime.now(timezone.utc)
        for m_node in sorted(missing_nodes):
            reconciliation["nodes"].append({
                "node_id": m_node,
                "name": f"Preserved Historical Node ({m_node})",
                "location": "Historical / Fixture Archive",
                "status": "archived",
                "created_at": now_dt,
                "updated_at": now_dt,
            })

    # 2. Check alert_notification_logs -> alerts
    if "alert_notification_logs" in source_tables and "alerts" in source_tables:
        src_cur.execute("SELECT DISTINCT alert_id FROM alert_notification_logs WHERE alert_id IS NOT NULL")
        notif_alert_ids = {row[0] for row in src_cur.fetchall()}
        src_cur.execute("SELECT id FROM alerts")
        existing_alert_ids = {row[0] for row in src_cur.fetchall()}
        missing_alerts = notif_alert_ids - existing_alert_ids
        if missing_alerts:
            logger.info("Found %d alert_ids in alert_notification_logs missing from 'alerts'.", len(missing_alerts))
            fallback_node = list(existing_nodes)[0] if existing_nodes else "node_overhead_a"
            now_dt = datetime.now(timezone.utc)
            for m_alert in sorted(missing_alerts):
                reconciliation["alerts"].append({
                    "id": m_alert,
                    "node_id": fallback_node,
                    "timestamp": now_dt,
                    "parameter": "system",
                    "value": 0.0,
                    "threshold": 0.0,
                    "severity": "INFO",
                    "message": f"Historical notification placeholder for alert {m_alert}",
                    "status": "RESOLVED",
                    "created_at": now_dt,
                })

    return reconciliation


def run_migration(
    source_sqlite: Path,
    target_url: str,
    dry_run: bool = False,
    on_existing: str = "refuse",
    batch_size: int = 500,
    reconcile_orphans: bool = True,
) -> Dict[str, Any]:
    """Execute the data migration from SQLite backup to target database.

    Args:
        source_sqlite: Path to verified SQLite backup file.
        target_url: SQLAlchemy connection string for target database.
        dry_run: If True, rollback transaction after validation.
        on_existing: 'refuse' (default), 'truncate', or 'skip'.
        batch_size: Number of records to insert per batch.
        reconcile_orphans: Whether to synthesize parent stubs for historical orphaned FKs.

    Returns:
        Structured migration report dict.
    """
    masked_url = get_masked_database_url(target_url)
    logger.info("Starting SQLite-to-target migration.")
    logger.info("Source: %s", source_sqlite)
    logger.info("Target: %s (dry_run=%s, on_existing=%s)", masked_url, dry_run, on_existing)

    # 1. Source Integrity Check
    integrity = verify_source_integrity(source_sqlite)
    if integrity != [("ok",)]:
        raise RuntimeError(f"Source SQLite integrity check failed: {integrity}")
    logger.info("Source SQLite backup passed integrity check (result: ok).")

    # 2. Connect to Source
    src_uri = f"file:{source_sqlite.resolve()}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    src_conn.row_factory = sqlite3.Row
    src_cur = src_conn.cursor()

    # Discover source tables
    src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
    source_tables = {row[0] for row in src_cur.fetchall()}

    # Check for foreign key reconciliations
    reconciled_parents = reconcile_missing_entities(src_cur, source_tables) if reconcile_orphans else {}

    # Discover valid forecast IDs for model_errors validation
    valid_forecast_ids: Set[int] = set()
    if "forecasts" in source_tables:
        src_cur.execute("SELECT id FROM forecasts")
        valid_forecast_ids = {row[0] for row in src_cur.fetchall()}

    # 3. Connect to Target Engine
    target_engine = create_app_engine(target_url)
    target_dialect = target_engine.dialect.name

    # Initialize target schema if tables do not exist
    Base.metadata.create_all(bind=target_engine)

    inspector = inspect(target_engine)
    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": str(source_sqlite),
        "target": masked_url,
        "target_dialect": target_dialect,
        "dry_run": dry_run,
        "on_existing": on_existing,
        "reconciled_entities": {k: len(v) for k, v in reconciled_parents.items()},
        "status": "IN_PROGRESS",
        "tables": {},
        "errors": [],
    }

    # 4. Check existing data in target
    with target_engine.connect() as conn:
        for table in MIGRATION_TABLE_ORDER:
            if inspector.has_table(table):
                res = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                cnt = res.scalar() or 0
                if cnt > 0:
                    if on_existing == "refuse":
                        src_conn.close()
                        raise RuntimeError(
                            f"Target table '{table}' already contains {cnt} records. "
                            "Aborting migration because --on-existing=refuse. "
                            "Target must be clean for a reliable, non-destructive migration."
                        )

    # 5. Execute Migration within a single Transaction
    try:
        with target_engine.begin() as conn:
            # Handle truncation if requested
            if on_existing == "truncate":
                logger.info("Truncating target tables in reverse dependency order...")
                for table in reversed(MIGRATION_TABLE_ORDER):
                    if inspector.has_table(table):
                        conn.execute(text(f'DELETE FROM "{table}"'))

            for table in MIGRATION_TABLE_ORDER:
                table_report: Dict[str, Any] = {
                    "source_rows": 0,
                    "reconciled_rows": 0,
                    "migrated_rows": 0,
                    "target_rows": 0,
                    "status": "SKIPPED",
                }

                if table not in source_tables:
                    logger.info("Table '%s' not present in source database; skipping.", table)
                    table_report["status"] = "SOURCE_TABLE_NOT_FOUND"
                    report["tables"][table] = table_report
                    continue

                if not inspector.has_table(table):
                    logger.warning("Table '%s' not defined in target schema; skipping.", table)
                    table_report["status"] = "TARGET_TABLE_NOT_FOUND"
                    report["tables"][table] = table_report
                    continue

                # Target table columns & types
                target_cols = {col["name"]: col["type"] for col in inspector.get_columns(table)}

                sa_table = Base.metadata.tables.get(table)
                if sa_table is None:
                    raise RuntimeError(f"Table '{table}' missing from SQLAlchemy Base.metadata.")

                # Read source row count
                src_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                src_count = src_cur.fetchone()[0]
                table_report["source_rows"] = src_count

                # Read all source records
                src_cur.execute(f'SELECT * FROM "{table}"')
                source_rows = src_cur.fetchall()

                # Transform and insert original source records FIRST to preserve IDs
                transformed_batch: List[Dict[str, Any]] = []
                for row in source_rows:
                    row_dict = dict(row)

                    # Special handling for model_errors -> non-existent forecast_id
                    if table == "model_errors" and "forecast_id" in row_dict:
                        f_id = row_dict["forecast_id"]
                        if f_id is not None and f_id not in valid_forecast_ids:
                            row_dict["forecast_id"] = None

                    t_record = transform_record(table, row_dict, target_cols)
                    transformed_batch.append(t_record)

                    if len(transformed_batch) >= batch_size:
                        conn.execute(sa_table.insert(), transformed_batch)
                        transformed_batch.clear()

                if transformed_batch:
                    conn.execute(sa_table.insert(), transformed_batch)
                    transformed_batch.clear()

                # Insert reconciled parent stubs AFTER original rows to avoid ID collisions
                stubs = reconciled_parents.get(table, [])
                if stubs:
                    logger.info("Inserting %d synthesized parent stubs into '%s' to satisfy relational integrity.", len(stubs), table)
                    conn.execute(sa_table.insert(), stubs)
                    table_report["reconciled_rows"] = len(stubs)

                table_report["migrated_rows"] = src_count + len(stubs)

                # Verify target count within transaction
                res = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                post_cnt = res.scalar() or 0
                table_report["target_rows"] = post_cnt

                expected_cnt = src_count + len(stubs)
                if post_cnt != expected_cnt:
                    raise ValueError(
                        f"Count mismatch in table '{table}': expected={expected_cnt}, target={post_cnt}"
                    )

                # Reset PostgreSQL Sequence for autoincrement primary key if applicable
                if target_dialect == "postgresql":
                    pk_cols = [c["name"] for c in inspector.get_columns(table) if c.get("primary_key")]
                    if len(pk_cols) == 1 and pk_cols[0] == "id":
                        seq_sql = text(
                            f"SELECT setval(pg_get_serial_sequence('\"{table}\"', 'id'), "
                            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM \"{table}\";"
                        )
                        conn.execute(seq_sql)
                        logger.info("Reset sequence for '%s.id'.", table)

                table_report["status"] = "VERIFIED_OK"
                report["tables"][table] = table_report
                logger.info("Table '%s': successfully migrated %d records (%d original + %d reconciled).", table, post_cnt, src_count, len(stubs))

            # Relationship integrity validation
            logger.info("Validating key relationships...")
            # Check sensor_readings -> nodes
            if "sensor_readings" in report["tables"] and report["tables"]["sensor_readings"]["source_rows"] > 0:
                orphans = conn.execute(
                    text('SELECT COUNT(*) FROM sensor_readings sr LEFT JOIN nodes n ON sr.node_id = n.node_id WHERE n.node_id IS NULL')
                ).scalar() or 0
                if orphans > 0:
                    raise ValueError(f"Foreign key violation: {orphans} orphaned sensor_readings detected.")

            # Check forecasts -> nodes
            if "forecasts" in report["tables"] and report["tables"]["forecasts"]["source_rows"] > 0:
                orphans = conn.execute(
                    text('SELECT COUNT(*) FROM forecasts f LEFT JOIN nodes n ON f.node_id = n.node_id WHERE n.node_id IS NULL')
                ).scalar() or 0
                if orphans > 0:
                    raise ValueError(f"Foreign key violation: {orphans} orphaned forecasts detected.")

            # Check alerts -> nodes
            if "alerts" in report["tables"] and report["tables"]["alerts"]["source_rows"] > 0:
                orphans = conn.execute(
                    text('SELECT COUNT(*) FROM alerts a LEFT JOIN nodes n ON a.node_id = n.node_id WHERE n.node_id IS NULL')
                ).scalar() or 0
                if orphans > 0:
                    raise ValueError(f"Foreign key violation: {orphans} orphaned alerts detected.")

            # Check issue_events -> hostel_issues
            if "issue_events" in report["tables"] and report["tables"]["issue_events"]["source_rows"] > 0:
                orphans = conn.execute(
                    text('SELECT COUNT(*) FROM issue_events ie LEFT JOIN hostel_issues hi ON ie.issue_id = hi.id WHERE hi.id IS NULL')
                ).scalar() or 0
                if orphans > 0:
                    raise ValueError(f"Foreign key violation: {orphans} orphaned issue_events detected.")

            # Check alert_notification_logs -> alerts
            if "alert_notification_logs" in report["tables"] and report["tables"]["alert_notification_logs"]["source_rows"] > 0:
                orphans = conn.execute(
                    text('SELECT COUNT(*) FROM alert_notification_logs anl LEFT JOIN alerts a ON anl.alert_id = a.id WHERE a.id IS NULL')
                ).scalar() or 0
                if orphans > 0:
                    raise ValueError(f"Foreign key violation: {orphans} orphaned alert_notification_logs detected.")

            logger.info("All key relationships validated successfully.")

            if dry_run:
                logger.info("Dry-run requested. Rolling back transaction.")
                conn.rollback()
                report["status"] = "DRY_RUN_PASSED"
            else:
                report["status"] = "SUCCESS"

    except Exception as exc:
        logger.exception("Migration failed: %s", exc)
        report["status"] = "FAILED"
        report["errors"].append(str(exc))
        raise
    finally:
        src_conn.close()
        target_engine.dispose()

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite backup to PostgreSQL.")
    parser.add_argument(
        "--source-sqlite",
        type=Path,
        default=None,
        help="Path to verified SQLite backup (.db). Defaults to newest in hydroguard-backend/data/backups/.",
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default=None,
        help="Target PostgreSQL/SQLAlchemy connection URL (defaults to DATABASE_URL / HYDROGUARD_DATABASE_URL).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate migration without committing changes.",
    )
    parser.add_argument(
        "--on-existing",
        choices=["refuse", "truncate", "skip"],
        default="refuse",
        help="Action if target tables contain data (default: refuse).",
    )
    parser.add_argument(
        "--no-reconcile-orphans",
        action="store_true",
        help="Disable automatic synthesis of missing parent records for historical orphaned foreign keys.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="File path to save the JSON migration report.",
    )

    args = parser.parse_args()

    # Determine source SQLite path
    source_sqlite = args.source_sqlite
    data_dir = BACKEND_ROOT / "data"
    if source_sqlite is None:
        source_sqlite = find_latest_verified_backup(data_dir)
        if source_sqlite is None:
            logger.error("No backup found in %s/backups. Please provide --source-sqlite.", data_dir)
            sys.exit(1)

    # Safety guard: Never run directly against active live DB unless explicitly verified
    active_db = (data_dir / "hydroguard.db").resolve()
    if source_sqlite.resolve() == active_db:
        logger.error(
            "CRITICAL SAFETY WARNING: %s appears to be the active live database file! "
            "Please run migration against a verified backup in data/backups/ instead.",
            source_sqlite,
        )
        sys.exit(1)

    # Determine target URL
    target_url = args.target_url or resolve_database_url()
    if target_url.startswith("sqlite") and "hydroguard.db" in target_url:
        logger.error(
            "Target URL (%s) points to default development SQLite database! "
            "Specify a valid PostgreSQL --target-url or set DATABASE_URL.",
            get_masked_database_url(target_url),
        )
        sys.exit(1)

    try:
        report = run_migration(
            source_sqlite=source_sqlite,
            target_url=target_url,
            dry_run=args.dry_run,
            on_existing=args.on_existing,
            reconcile_orphans=not args.no_reconcile_orphans,
        )
        print("\n" + "=" * 65)
        print(f"MIGRATION RESULT: {report['status']}")
        print("=" * 65)
        for tbl, info in report.get("tables", {}).items():
            print(f"  {tbl:32} Source: {info.get('source_rows', 0):4} | Migrated: {info.get('migrated_rows', 0):4} | Status: {info.get('status')}")
        print("=" * 65)

        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.report_json, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"Report written to: {args.report_json}")

    except Exception as exc:
        print(f"\nMigration failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
