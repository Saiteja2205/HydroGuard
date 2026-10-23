-- Downgrade: 001_create_raw_telemetry_observations_downgrade.sql
-- Description: Reverses 001_create_raw_telemetry_observations.sql
-- Warning: Dropping this table will remove raw telemetry audit history.

DROP INDEX IF EXISTS "idx_raw_telemetry_ingested_at";
DROP INDEX IF EXISTS "idx_raw_telemetry_overall_status";
DROP INDEX IF EXISTS "idx_raw_telemetry_source_timestamp";
DROP INDEX IF EXISTS "idx_raw_telemetry_channel_entry";
DROP TABLE IF EXISTS "raw_telemetry_observations";
