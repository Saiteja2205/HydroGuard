# HydroGuard Database Migrations

This directory contains standalone, reversible SQL migrations for schema changes.

## Migration Convention
The HydroGuard repository does not use Alembic. Instead:
1. ORM schemas are declared in `app.db.models` inheriting from `Base`.
2. Clean database initializations (and test databases) invoke `init_db()` which executes `Base.metadata.create_all(bind=engine)`.
3. Existing databases can be safely upgraded using the SQL migration files provided here.

## Files
- `001_create_raw_telemetry_observations.sql`: Creates `raw_telemetry_observations` table and indexes.
- `001_create_raw_telemetry_observations_downgrade.sql`: Reversible downgrade script.

## Safety Note
These scripts are intentionally not executed automatically against `data/hydroguard.db` without operator instruction.
