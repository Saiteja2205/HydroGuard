-- Migration: 001_create_raw_telemetry_observations.sql
-- Description: Creates raw_telemetry_observations table for raw ThingSpeak telemetry auditing
-- Target: SQLite (and compatible with PostgreSQL)
-- Note: Do NOT execute directly on active production database without change approval.

CREATE TABLE IF NOT EXISTS "raw_telemetry_observations" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "source" VARCHAR(50) NOT NULL DEFAULT 'THINGSPEAK',
    "channel_id" VARCHAR(64) NOT NULL,
    "entry_id" INTEGER,
    "source_timestamp" DATETIME,
    "ingested_at" DATETIME NOT NULL,
    "raw_payload" JSON,
    "raw_ph" VARCHAR(64),
    "raw_tds" VARCHAR(64),
    "raw_turbidity" VARCHAR(64),
    "raw_temperature" VARCHAR(64),
    "raw_red" VARCHAR(64),
    "raw_green" VARCHAR(64),
    "raw_blue" VARCHAR(64),
    "overall_status" VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    "validation_results" JSON,
    "validation_version" VARCHAR(32) NOT NULL DEFAULT '2.0.0',
    "rejection_reason" VARCHAR(500),
    "is_persisted_normalized" BOOLEAN NOT NULL DEFAULT 0,
    "normalized_reading_id" INTEGER REFERENCES "sensor_readings" ("id") ON DELETE SET NULL,
    "processing_status" VARCHAR(32) NOT NULL DEFAULT 'INGESTED',
    "error_message" VARCHAR(500),
    CONSTRAINT "uq_raw_telemetry_channel_entry" UNIQUE ("channel_id", "entry_id")
);

CREATE INDEX IF NOT EXISTS "idx_raw_telemetry_channel_entry" ON "raw_telemetry_observations" ("channel_id", "entry_id");
CREATE INDEX IF NOT EXISTS "idx_raw_telemetry_source_timestamp" ON "raw_telemetry_observations" ("source_timestamp");
CREATE INDEX IF NOT EXISTS "idx_raw_telemetry_overall_status" ON "raw_telemetry_observations" ("overall_status");
CREATE INDEX IF NOT EXISTS "idx_raw_telemetry_ingested_at" ON "raw_telemetry_observations" ("ingested_at");
