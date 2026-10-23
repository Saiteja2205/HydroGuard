"""Comprehensive tests for Phase 3: Raw Telemetry Preservation and Auditability.

Verifies:
1. Valid observation: raw and normalized records are persisted; checkpoint advances.
2. Missing sensor parameter: raw payload is retained; normalized handling follows existing rules.
3. Zero-value dropout: original "0.0" is preserved in raw storage and does not enter normal readings.
4. Negative or out-of-bounds: raw record remains available and is excluded from normal readings.
5. SUSPECT_HIGH observation: raw value is preserved and normalized reading created.
6. Duplicate ThingSpeak entry: retry does not create duplicate raw or normalized records.
7. Raw persistence failure: checkpoint does not advance past the unrecorded observation.
8. Normalized insertion failure: raw observation remains durable and checkpoint does not skip.
9. Batch containing multiple entries: a failed entry cannot be silently skipped by checkpoint advancement.
10. Missing or malformed timestamps and payload values are handled without losing original payload.
11. Existing alert behavior remains correct: dropouts cannot create or auto-resolve alerts.
12. Existing forecasting pipeline does not consume rejected values or fabricate zeros.
"""

from datetime import datetime, timezone
from typing import Any, Mapping
import pytest
from unittest.mock import patch

from app.db.database import get_db_context, init_db
from app.db.models import (
    Alert,
    Node,
    RawTelemetryObservation,
    SensorReading,
    ThingSpeakMonitorCheckpoint,
    ThresholdConfig,
)
from app.db.repositories import (
    AlertRepository,
    NodeRepository,
    RawTelemetryRepository,
    SensorReadingRepository,
    ThingSpeakMonitorRepository,
)
from app.services.thingspeak_alert_monitor import ThingSpeakAlertMonitor
from ml.data.sensor_validation import SensorQualityFlag
from ml.services.thingspeak_service import ThingSpeakConfig, parse_feeds


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def setup_isolated_test_db():
    """Ensure clean test tables for each test."""
    init_db()
    with get_db_context() as db:
        db.query(Alert).filter(Alert.node_id.like("thingspeak-%") | Alert.node_id.like("test_%")).delete()
        db.query(SensorReading).filter(SensorReading.node_id.like("thingspeak-%") | SensorReading.node_id.like("test_%")).delete()
        db.query(RawTelemetryObservation).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()
    yield
    with get_db_context() as db:
        db.query(Alert).filter(Alert.node_id.like("thingspeak-%") | Alert.node_id.like("test_%")).delete()
        db.query(SensorReading).filter(SensorReading.node_id.like("thingspeak-%") | SensorReading.node_id.like("test_%")).delete()
        db.query(RawTelemetryObservation).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()


# ---------------------------------------------------------------------------
# Test Case 1: Valid observation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_valid_observation_persists_raw_and_normalized():
    """Verify that a valid observation is saved both in raw storage and normalized sensor_readings."""
    channel_id = "888001"
    node_id = f"thingspeak-{channel_id}"
    feed = {
        "created_at": "2026-10-23T10:00:00Z",
        "entry_id": 1,
        "field1": "7.35",
        "field2": "240.0",
        "field3": "2.10",
        "field4": "25.5",
        "field5": "45",
        "field6": "50",
        "field7": "55",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    processed = await monitor.poll_once()
    assert processed == 1

    with get_db_context() as db:
        # Check raw telemetry record
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs is not None
        assert raw_obs.overall_status == "VALID"
        assert raw_obs.raw_ph == "7.35"
        assert raw_obs.raw_tds == "240.0"
        assert raw_obs.raw_turbidity == "2.10"
        assert raw_obs.raw_temperature == "25.5"
        assert raw_obs.raw_red == "45"
        assert raw_obs.raw_green == "50"
        assert raw_obs.raw_blue == "55"
        assert raw_obs.is_persisted_normalized is True
        assert raw_obs.normalized_reading_id is not None
        assert raw_obs.processing_status == "PROCESSED_NORMALIZED"

        # Check normalized SensorReading record
        reading = db.query(SensorReading).filter_by(id=raw_obs.normalized_reading_id).first()
        assert reading is not None
        assert reading.node_id == node_id
        assert float(reading.ph) == pytest.approx(7.35)
        assert float(reading.tds) == pytest.approx(240.0)
        assert float(reading.turbidity) == pytest.approx(2.10)
        assert float(reading.temperature) == pytest.approx(25.5)
        assert reading.red == 45
        assert reading.green == 50
        assert reading.blue == 55

        # Check checkpoint advanced
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp is not None
        assert cp.last_entry_id == 1


# ---------------------------------------------------------------------------
# Test Case 2: Missing sensor parameter
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_missing_sensor_parameter_retained_in_raw():
    """Verify missing optional parameter (temp) normalizes with temp=NULL; missing required skips normalized."""
    channel_id = "888002"
    # Feed A: optional temp is None -> normalizes with temperature=None
    feed_a = {
        "created_at": "2026-10-23T10:05:00Z",
        "entry_id": 1,
        "field1": "7.20",
        "field2": "210.0",
        "field3": "1.50",
        "field4": None,  # temp missing
    }

    monitor_a = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed_a],
    )
    await monitor_a.poll_once()

    with get_db_context() as db:
        raw_a = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_a is not None
        assert raw_a.raw_temperature is None
        assert raw_a.is_persisted_normalized is True
        norm_a = db.query(SensorReading).filter_by(id=raw_a.normalized_reading_id).first()
        assert norm_a is not None
        assert norm_a.temperature is None
        assert float(norm_a.ph) == pytest.approx(7.20)

    # Feed B: required pH is None -> raw retained, excluded from normalized
    feed_b = {
        "created_at": "2026-10-23T10:10:00Z",
        "entry_id": 2,
        "field1": None,  # pH missing
        "field2": "210.0",
        "field3": "1.50",
        "field4": "25.0",
    }
    monitor_b = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed_b],
    )
    await monitor_b.poll_once()

    with get_db_context() as db:
        raw_b = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 2)
        assert raw_b is not None
        assert raw_b.raw_ph is None
        assert raw_b.is_persisted_normalized is False
        assert raw_b.processing_status == "SKIPPED_INELIGIBLE"
        assert "pH: MISSING" in (raw_b.rejection_reason or "")

        # Sensor readings count should still be 1 (only feed_a)
        count = SensorReadingRepository.get_count_by_node(db, f"thingspeak-{channel_id}")
        assert count == 1


# ---------------------------------------------------------------------------
# Test Case 3: Zero-value dropout preservation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_zero_value_dropout_preserved_raw_and_excluded_normalized():
    """Verify TDS=0.0 and pH=0.0 retain literal '0.0' in raw storage and are excluded from sensor_readings."""
    channel_id = "888003"
    feed = {
        "created_at": "2026-10-23T10:15:00Z",
        "entry_id": 1,
        "field1": "0.0",  # pH dropout (0V ADC)
        "field2": "0.0",  # TDS dropout (unimmersed/open-circuit)
        "field3": "1.5",
        "field4": "25.0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs is not None
        # Literal "0.0" must be preserved; NEVER converted to NULL in raw storage!
        assert raw_obs.raw_ph == "0.0"
        assert raw_obs.raw_tds == "0.0"
        assert raw_obs.raw_payload["field1"] == "0.0"
        assert raw_obs.raw_payload["field2"] == "0.0"

        assert raw_obs.overall_status in ("DROPOUT", "PARTIALLY_VALID")
        assert raw_obs.is_persisted_normalized is False
        assert raw_obs.processing_status == "SKIPPED_INELIGIBLE"

        # Verify not in sensor_readings
        count = SensorReadingRepository.get_count_by_node(db, f"thingspeak-{channel_id}")
        assert count == 0

        # Checkpoint advances because raw record was safely preserved
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp.last_entry_id == 1


# ---------------------------------------------------------------------------
# Test Case 4: Negative and out-of-bounds observations
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_out_of_bounds_observation_preserved_in_raw():
    """Verify negative TDS and pH 16.5 remain auditable in raw storage and never enter sensor_readings."""
    channel_id = "888004"
    feed = {
        "created_at": "2026-10-23T10:20:00Z",
        "entry_id": 1,
        "field1": "16.5",   # Out of bounds pH
        "field2": "-25.0",  # Negative TDS
        "field3": "1.2",
        "field4": "135.0",  # Out of bounds temp (>125 DS18B20 hardware limit)
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs is not None
        assert raw_obs.raw_ph == "16.5"
        assert raw_obs.raw_tds == "-25.0"
        assert raw_obs.raw_temperature == "135.0"
        assert raw_obs.is_persisted_normalized is False
        assert raw_obs.processing_status == "SKIPPED_INELIGIBLE"
        assert "OUT_OF_BOUNDS" in (raw_obs.rejection_reason or "")

        count = SensorReadingRepository.get_count_by_node(db, f"thingspeak-{channel_id}")
        assert count == 0


# ---------------------------------------------------------------------------
# Test Case 5: SUSPECT_HIGH observation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_suspect_high_observation_preserved_and_normalized():
    """Verify turbidity > 1000 NTU is flagged SUSPECT_HIGH, preserved in raw, and normalized for operator review."""
    channel_id = "888005"
    feed = {
        "created_at": "2026-10-23T10:25:00Z",
        "entry_id": 1,
        "field1": "7.30",
        "field2": "250.0",
        "field3": "1200.0",  # Severe silt runoff / TS-300B saturation
        "field4": "24.0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs is not None
        assert raw_obs.raw_turbidity == "1200.0"
        assert raw_obs.validation_results["turbidity"]["flag"] == "SUSPECT_HIGH"
        assert raw_obs.is_persisted_normalized is True

        reading = db.query(SensorReading).filter_by(id=raw_obs.normalized_reading_id).first()
        assert reading is not None
        assert float(reading.turbidity) == pytest.approx(1200.0)


# ---------------------------------------------------------------------------
# Test Case 6: Duplicate entry retry idempotency
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_duplicate_thingspeak_entry_retry_idempotency():
    """Verify polling the same feed repeatedly does not duplicate raw or normalized records."""
    channel_id = "888006"
    feed = {
        "created_at": "2026-10-23T10:30:00Z",
        "entry_id": 100,
        "field1": "7.10",
        "field2": "220.0",
        "field3": "1.80",
        "field4": "25.0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )

    # Poll 1
    p1 = await monitor.poll_once()
    assert p1 == 1

    # Poll 2 (same feed)
    p2 = await monitor.poll_once()
    assert p2 == 0

    with get_db_context() as db:
        raw_count = RawTelemetryRepository.get_count_by_channel(db, channel_id)
        assert raw_count == 1

        norm_count = SensorReadingRepository.get_count_by_node(db, f"thingspeak-{channel_id}")
        assert norm_count == 1


# ---------------------------------------------------------------------------
# Test Case 7: Raw persistence failure blocks checkpoint
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_raw_persistence_failure_blocks_checkpoint_advancement():
    """Verify that if saving raw telemetry fails, checkpoint does not advance past unrecorded observation."""
    channel_id = "888007"
    feed = {
        "created_at": "2026-10-23T10:35:00Z",
        "entry_id": 1,
        "field1": "7.40",
        "field2": "230.0",
        "field3": "1.60",
        "field4": "24.5",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )

    # Simulate raw persistence error (e.g. disk full / database locked)
    with patch.object(RawTelemetryRepository, "create_or_get", side_effect=RuntimeError("Simulated raw DB write failure")):
        processed = await monitor.poll_once()
        assert processed == 0

    with get_db_context() as db:
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        # Checkpoint MUST NOT have advanced to entry 1!
        assert cp is None or cp.last_entry_id is None

    # Now run without error -> succeeds and advances checkpoint
    processed_retry = await monitor.poll_once()
    assert processed_retry == 1

    with get_db_context() as db:
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp.last_entry_id == 1


# ---------------------------------------------------------------------------
# Test Case 8: Normalized insertion failure retains raw record
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_normalized_insertion_failure_retains_raw_record():
    """Verify raw record remains durable even if normalized persistence raises an unexpected exception."""
    channel_id = "888008"
    feed = {
        "created_at": "2026-10-23T10:40:00Z",
        "entry_id": 1,
        "field1": "7.50",
        "field2": "260.0",
        "field3": "2.00",
        "field4": "25.0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )

    # Simulate unexpected failure during SensorReadingRepository.create
    with patch.object(SensorReadingRepository, "create", side_effect=RuntimeError("Simulated normalized DB crash")):
        await monitor.poll_once()

    with get_db_context() as db:
        # Raw record MUST exist!
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs is not None
        assert raw_obs.processing_status == "NORMALIZATION_FAILED"
        assert "Simulated normalized DB crash" in (raw_obs.error_message or "")

        # Checkpoint must NOT advance past the failed normalized reading so retry can occur
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp is None or cp.last_entry_id is None

    # On next poll without crash, retry succeeds
    p_retry = await monitor.poll_once()
    assert p_retry == 1

    with get_db_context() as db:
        raw_obs_retry = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 1)
        assert raw_obs_retry.is_persisted_normalized is True
        assert raw_obs_retry.processing_status == "PROCESSED_NORMALIZED"
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp.last_entry_id == 1


# ---------------------------------------------------------------------------
# Test Case 9: Batch multi-entry failure cannot skip failed entry
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_batch_multi_entry_failure_cannot_skip_failed_entry():
    """Verify that if feed 2 in [feed 1, feed 2, feed 3] fails, checkpoint stops at feed 1 and does not skip feed 2."""
    channel_id = "888009"
    f1 = {"created_at": "2026-10-23T10:45:00Z", "entry_id": 10, "field1": "7.2", "field2": "200.0", "field3": "1.0", "field4": "25.0"}
    f2 = {"created_at": "2026-10-23T10:46:00Z", "entry_id": 11, "field1": "7.3", "field2": "210.0", "field3": "1.1", "field4": "25.0"}
    f3 = {"created_at": "2026-10-23T10:47:00Z", "entry_id": 12, "field1": "7.4", "field2": "220.0", "field3": "1.2", "field4": "25.0"}

    original_create_or_get = RawTelemetryRepository.create_or_get

    def _flaky_raw_create(db, channel_id, entry_id, source_timestamp, **kwargs):
        if entry_id == 11:
            raise RuntimeError("Simulated failure at entry 11")
        return original_create_or_get(db, channel_id, entry_id, source_timestamp, **kwargs)

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [f1, f2, f3],
    )

    with patch.object(RawTelemetryRepository, "create_or_get", side_effect=_flaky_raw_create):
        await monitor.poll_once()

    with get_db_context() as db:
        # Feed 10 must be recorded
        assert RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 10) is not None
        # Feed 11 and 12 must NOT be in DB
        assert RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 11) is None
        assert RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 12) is None

        # Checkpoint MUST be exactly 10, NOT 11 and NOT 12!
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp.last_entry_id == 10


# ---------------------------------------------------------------------------
# Test Case 10: Malformed timestamp and payload values
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_malformed_timestamp_and_payload_preserves_raw_data():
    """Verify unparseable timestamps and string values are preserved without crashing monitor."""
    channel_id = "888010"
    feed = {
        "created_at": "completely-invalid-date-string",
        "entry_id": 999,
        "field1": "not-a-number",
        "field2": "$$$",
        "field3": "---",
        "field4": "err",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    processed = await monitor.poll_once()
    assert processed == 1

    with get_db_context() as db:
        raw_obs = RawTelemetryRepository.get_by_channel_and_entry(db, channel_id, 999)
        assert raw_obs is not None
        assert raw_obs.source_timestamp is None  # Unparseable timestamp yields None
        assert raw_obs.ingested_at is not None   # Ingestion timestamp is valid UTC now
        assert raw_obs.raw_ph == "not-a-number"
        assert raw_obs.raw_tds == "$$$"
        assert raw_obs.overall_status == "MISSING"
        assert raw_obs.is_persisted_normalized is False

        # No corrupt reading in sensor_readings
        count = SensorReadingRepository.get_count_by_node(db, f"thingspeak-{channel_id}")
        assert count == 0


# ---------------------------------------------------------------------------
# Test Case 11: Existing alert behavior remains correct
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_existing_alert_behavior_dropouts_cannot_create_or_resolve_alerts():
    """Verify sensor dropouts (pH=0, TDS=0) do not trigger false alerts and do not auto-resolve active alerts."""
    channel_id = "888011"
    node_id = f"thingspeak-{channel_id}"
    now = datetime.now(timezone.utc)

    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Test Node", "Lab")
        # Create an existing active alert for high TDS
        AlertRepository.create(
            db=db,
            node_id=node_id,
            timestamp=now,
            parameter="TDS",
            value=650.0,
            threshold=500.0,
            severity="WARNING",
            message="TDS above threshold",
            status="ACTIVE",
        )

    # Feed with TDS=0.0 (dropout) and pH=0.0 (dropout)
    dropout_feed = {
        "created_at": "2026-10-23T11:00:00Z",
        "entry_id": 1,
        "field1": "0.0",
        "field2": "0.0",
        "field3": "1.5",
        "field4": "25.0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [dropout_feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        # 1. TDS alert must still be ACTIVE (not resolved by TDS=0.0 dropout!)
        active = AlertRepository.get_active_by_node(db, node_id)
        assert len(active) == 1
        assert active[0].parameter == "TDS"

        # 2. No false low-pH alert was generated by pH=0.0 dropout
        ph_alerts = db.query(Alert).filter_by(node_id=node_id, parameter="pH").all()
        assert len(ph_alerts) == 0


# ---------------------------------------------------------------------------
# Test Case 12: Forecasting pipeline never consumes rejected values
# ---------------------------------------------------------------------------

def test_forecasting_pipeline_never_consumes_rejected_values():
    """Verify parse_feeds gap-filling never propagates rejected 0.0 or negative values into model values."""
    config = ThingSpeakConfig(channel_id="888012", results=3)
    feeds = [
        {"created_at": "2026-10-23T10:00:00Z", "entry_id": 1, "field1": "7.3", "field2": "220.0", "field3": "1.5", "field4": "24.0"},
        {"created_at": "2026-10-23T10:01:00Z", "entry_id": 2, "field1": "0.0", "field2": "0.0", "field3": "-2.0", "field4": "0.0"},  # all dropouts/invalid
        {"created_at": "2026-10-23T10:02:00Z", "entry_id": 3, "field1": "7.5", "field2": "230.0", "field3": "1.7", "field4": "25.0"},
    ]

    window = parse_feeds(feeds, config)
    # Row 1 must be causally forward-filled from Row 0, NEVER 0.0 or negative!
    row1 = window.values[1]
    assert row1[0] == pytest.approx(7.3)
    assert row1[1] == pytest.approx(220.0)
    assert row1[2] == pytest.approx(1.5)
    assert row1[3] == pytest.approx(24.0)

    # Gaps must be reported transparently in metadata
    assert window.forward_filled > 0
