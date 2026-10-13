"""Migrate the HydroGuard database to the real single-tank deployment.

The deployed hostel has one building, one block and one water tank. The
database still carried two example nodes created by the old demo seeder:

    node_overhead_b   "Overhead Tank B"   "Hostel Block B"
    node_mess_ground  "Mess Ground Water" "Mess Area"

Each holds simulated ``HISTORICAL_DEMO`` readings for a block that does not
exist in the real hostel.

Safety rules enforced by this script:

  * a timestamped backup is taken before anything is written;
  * a node is removed only when it is *provably* a demo fixture: it is not a
    configured tank, it has no live sensor readings, and no forecasts, model
    errors, ensemble weights, alerts or calibrations depend on it;
  * anything failing that check is reported and left untouched;
  * the configured tank is never a removal candidate;
  * accounts, complaints, lost-and-found items, notices, thresholds and the
    200-observation development dataset are never touched.

Usage::

    python scripts/migrate_single_hostel.py           # dry run, report only
    python scripts/migrate_single_hostel.py --apply   # perform the migration

The script is idempotent: running it again reports nothing left to do.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func

from app.core.hostel_config import (
    CANONICAL_NODE_ID,
    TANKS,
    block_name,
    canonical_node_name,
    tank_node_ids,
    validate as validate_configuration,
)
from app.db.database import DB_PATH, get_db_context, init_db
from app.db.auth_models import HydroGuardUser
from app.db.models import Alert, EnsembleWeight, Forecast, ModelError, Node, SensorCalibration, SensorReading

#: Provenance that can only come from seeded/demo generation.
DEMO_SOURCES = (
    "DEMO",
    "HISTORICAL_DEMO",
    "HISTORICAL_OR_SIMULATED",
    "SIMULATED",
    "SIMULATED_DEVELOPMENT",
)

#: Provenance that proves a physical sensor has reported for this node.
LIVE_SOURCES = ("REAL_SENSOR", "THINGSPEAK", "ESP32")

#: Tables with a ``node_id`` foreign key that represent real analysis output.
DEPENDENT_TABLES = (
    ("forecasts", Forecast),
    ("model_errors", ModelError),
    ("ensemble_weights", EnsembleWeight),
    ("alerts", Alert),
    ("sensor_calibrations", SensorCalibration),
)


def _describe_node(db, node: Node) -> dict:
    readings = (
        db.query(func.count(SensorReading.id))
        .filter(SensorReading.node_id == node.node_id)
        .scalar()
        or 0
    )
    live = (
        db.query(func.count(SensorReading.id))
        .filter(
            SensorReading.node_id == node.node_id,
            func.upper(SensorReading.source).in_(LIVE_SOURCES),
        )
        .scalar()
        or 0
    )
    demo = (
        db.query(func.count(SensorReading.id))
        .filter(
            SensorReading.node_id == node.node_id,
            func.upper(SensorReading.source).in_(DEMO_SOURCES),
        )
        .scalar()
        or 0
    )
    dependents = {
        table: (
            db.query(func.count(model.id)).filter(model.node_id == node.node_id).scalar() or 0
        )
        for table, model in DEPENDENT_TABLES
    }
    return {
        "node_id": node.node_id,
        "name": node.name,
        "location": node.location,
        "status": node.status,
        "readings": readings,
        "live_readings": live,
        "demo_readings": demo,
        "dependents": dependents,
    }


def _is_confirmed_fixture(info: dict) -> tuple[bool, list[str]]:
    """Return (safe_to_remove, reasons_if_not)."""
    reasons = []
    if info["node_id"] in tank_node_ids():
        reasons.append("it is a configured hostel tank")
    if info["live_readings"]:
        reasons.append(f"it has {info['live_readings']} live sensor readings")
    extra = {name: count for name, count in info["dependents"].items() if count}
    if extra:
        joined = ", ".join(f"{name}={count}" for name, count in sorted(extra.items()))
        reasons.append(f"analysis output depends on it ({joined})")
    if info["readings"] != info["demo_readings"] + info["live_readings"]:
        reasons.append("it has readings with unrecognised provenance")
    return (not reasons, reasons)


def make_backup() -> Path:
    """Copy the database to a timestamped file before any write."""
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / f"hydroguard_pre_hostel_config_{stamp}.db"
    shutil.copy2(DB_PATH, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the migration. Without this flag nothing is written.",
    )
    args = parser.parse_args()

    validate_configuration()
    database_existed = DB_PATH.exists()
    init_db()

    print("HydroGuard single-hostel migration")
    print("=" * 70)
    print(f"database     : {DB_PATH}")
    print(f"mode         : {'APPLY' if args.apply else 'DRY RUN (no changes)'}")
    print(f"deployed tank: {CANONICAL_NODE_ID} -> {canonical_node_name()}")
    print()

    if args.apply and not database_existed:
        print("Nothing to migrate: database file does not exist yet.")
        return 0

    backup_path = None
    if args.apply:
        backup_path = make_backup()
        print(f"backup       : {backup_path}")

    changed = False
    with get_db_context() as db:
        nodes = db.query(Node).order_by(Node.node_id).all()
        print(f"nodes found  : {len(nodes)}")
        print()

        # 1. Report (and only with --apply, remove) non-deployed demo nodes.
        for node in nodes:
            info = _describe_node(db, node)
            safe, reasons = _is_confirmed_fixture(info)
            marker = "DEPLOYED" if info["node_id"] in tank_node_ids() else (
                "REMOVE" if safe else "KEEP"
            )
            print(
                f"[{marker:8}] {info['node_id']:20} name={info['name']!r} "
                f"location={info['location']!r} readings={info['readings']}"
            )
            if info["node_id"] in tank_node_ids():
                continue
            if not safe:
                for reason in reasons:
                    print(f"           kept because {reason}")
                continue
            if not args.apply:
                continue

            removed_readings = (
                db.query(SensorReading)
                .filter(SensorReading.node_id == info["node_id"])
                .delete(synchronize_session=False)
            )
            db.delete(node)
            changed = True
            print(f"           removed {removed_readings} demo readings and the node row")

        # 2. Restore canonical display metadata on the deployed tank.
        canonical = db.query(Node).filter(Node.node_id == CANONICAL_NODE_ID).first()
        if canonical is None:
            print(f"\nWARNING: configured tank {CANONICAL_NODE_ID} is not present in the database.")
        else:
            expected_name = canonical_node_name()
            expected_location = block_name(TANKS[0]["block_id"])
            renames = []
            if (canonical.name or "").strip() != expected_name:
                renames.append(f"name {canonical.name!r} -> {expected_name!r}")
                if args.apply:
                    canonical.name = expected_name
                    changed = True
            if (canonical.location or "").strip() != expected_location:
                renames.append(f"location {canonical.location!r} -> {expected_location!r}")
                if args.apply:
                    canonical.location = expected_location
                    changed = True
            if renames:
                print(f"\n[{'UPDATED' if args.apply else 'WOULD UPDATE'}] {CANONICAL_NODE_ID}: " + "; ".join(renames))
            else:
                print(f"\n[OK] {CANONICAL_NODE_ID} already carries the canonical name and location")

        if args.apply:
            db.commit()

        # 3. Preservation report: what must NOT have changed.
        print("\nPreserved data (verified after the migration):")
        print(f"  accounts          : {db.query(HydroGuardUser).count()}")
        for table, model in DEPENDENT_TABLES:
            print(f"  {table:18}: {db.query(func.count(model.id)).scalar() or 0}")
        for tank in TANKS:
            count = (
                db.query(func.count(SensorReading.id))
                .filter(SensorReading.node_id == tank["node_id"])
                .scalar()
                or 0
            )
            print(f"  readings/{tank['node_id']}: {count}")

    print()
    if not args.apply:
        print("Dry run complete. Re-run with --apply to perform the migration.")
    elif changed:
        print("Migration applied. Restart the backend so it reloads the node list.")
    else:
        print("Nothing to change: the database already matches the deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
