"""Tests for parameter-specific sensor validation, data quality flags, and alerting/model integrity."""

from datetime import datetime, timedelta, timezone
import math
import pytest
from sqlalchemy import text

from app.db.database import get_db_context, init_db
from app.db.models import Alert, Node, SensorReading, ThingSpeakMonitorCheckpoint, ThresholdConfig
from app.db.repositories import AlertRepository, NodeRepository, SensorReadingRepository
from app.services.alert_service import AlertService, is_physically_valid
from app.services.thingspeak_alert_monitor import ThingSpeakAlertMonitor, _feed_sort_key
from ml.data.sensor_validation import (
    ParameterValidationResult,
    SensorQualityFlag,
    coerce_model_parameter,
    is_physically_valid_for_alerts,
    validate_parameter,
    validate_reading_payload,
)
from ml.services.thingspeak_service import (
    ThingSpeakConfig,
    _coerce_value,
    parse_feeds,
    parse_history_readings,
)


@pytest.fixture(autouse=True)
def setup_isolated_db():
    """Ensure clean test tables for each test."""
    init_db()
    with get_db_context() as db:
        db.query(Alert).filter(Alert.node_id.like("test_%") | Alert.node_id.like("thingspeak-%")).delete()
        db.query(SensorReading).filter(SensorReading.node_id.like("test_%") | SensorReading.node_id.like("thingspeak-%")).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()
    yield
    with get_db_context() as db:
        db.query(Alert).filter(Alert.node_id.like("test_%") | Alert.node_id.like("thingspeak-%")).delete()
        db.query(SensorReading).filter(SensorReading.node_id.like("test_%") | SensorReading.node_id.like("thingspeak-%")).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()


# ---------------------------------------------------------------------------
# Part 1: Physical Boundary & Validation Rules
# ---------------------------------------------------------------------------

def test_valid_boundary_values():
    """Verify parameters at valid boundaries pass validation as VALID."""
    # pH valid boundary
    assert validate_parameter("pH", 0.06).flag == SensorQualityFlag.VALID
    assert validate_parameter("pH", 7.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("pH", 14.0).flag == SensorQualityFlag.VALID

    # TDS valid boundary
    assert validate_parameter("TDS", 1.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("TDS", 250.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("TDS", 2000.0).flag == SensorQualityFlag.VALID

    # Turbidity valid boundary
    assert validate_parameter("turbidity", 0.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("turbidity", 5.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("turbidity", 1000.0).flag == SensorQualityFlag.VALID

    # Temperature valid boundary
    assert validate_parameter("temperature", 1.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("temperature", 25.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("temperature", 60.0).flag == SensorQualityFlag.VALID


def test_ph_out_of_bounds_and_dropout():
    """Verify pH < 0, pH > 14 are OUT_OF_BOUNDS and pH <= 0.05 is DROPOUT."""
    # Out of physical bounds
    res_neg = validate_parameter("pH", -0.5)
    assert res_neg.flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert res_neg.is_valid_for_model is False
    assert res_neg.is_valid_for_alerts is False

    res_high = validate_parameter("pH", 14.1)
    assert res_high.flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert res_high.is_valid_for_model is False

    # Sensor dropout (0V ADC / disconnected probe)
    res_zero = validate_parameter("pH", 0.0)
    assert res_zero.flag == SensorQualityFlag.DROPOUT
    assert res_zero.is_valid_for_model is False
    assert res_zero.is_valid_for_alerts is False
    assert "0V ADC" in res_zero.reason or "dropout" in res_zero.reason

    res_low = validate_parameter("pH", 0.05)
    assert res_low.flag == SensorQualityFlag.DROPOUT


def test_tds_negative_and_zero_dropout():
    """Verify negative TDS is OUT_OF_BOUNDS and TDS == 0.0 is flagged as DROPOUT."""
    res_neg = validate_parameter("TDS", -1.0)
    assert res_neg.flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert res_neg.is_valid_for_model is False
    assert res_neg.is_valid_for_alerts is False

    res_zero = validate_parameter("TDS", 0.0)
    assert res_zero.flag == SensorQualityFlag.DROPOUT
    assert res_zero.is_valid_for_model is False
    assert res_zero.is_valid_for_alerts is False
    assert "disconnect" in res_zero.reason or "unimmersed" in res_zero.reason


def test_turbidity_negative_and_suspect_high():
    """Verify negative turbidity is OUT_OF_BOUNDS and > 1000 NTU is SUSPECT_HIGH."""
    res_neg = validate_parameter("turbidity", -0.5)
    assert res_neg.flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert res_neg.is_valid_for_model is False

    # High turbidity is retained for review rather than deleted
    res_high = validate_parameter("turbidity", 1500.0)
    assert res_high.flag == SensorQualityFlag.SUSPECT_HIGH
    assert res_high.is_valid_for_model is True
    assert res_high.is_valid_for_alerts is True
    assert "review" in res_high.reason


def test_temperature_hardware_specification_and_dropouts():
    """Verify temperature against DS18B20 hardware specs and disconnect codes."""
    # Hardware bounds [-55, 125] °C
    assert validate_parameter("temperature", -60.0).flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert validate_parameter("temperature", 130.0).flag == SensorQualityFlag.OUT_OF_BOUNDS

    # Hardware disconnect / error codes
    res_disc = validate_parameter("temperature", -127.0)
    assert res_disc.flag == SensorQualityFlag.DROPOUT
    assert res_disc.is_valid_for_model is False

    res_reset = validate_parameter("temperature", 85.0)
    assert res_reset.flag == SensorQualityFlag.DROPOUT
    assert res_reset.is_valid_for_model is False

    # Liquid water storage cold dropout (<= 0.5 °C)
    res_zero = validate_parameter("temperature", 0.0)
    assert res_zero.flag == SensorQualityFlag.DROPOUT

    # Plausible hot temperature (> 60 °C but <= 125 °C) flagged for review
    res_hot = validate_parameter("temperature", 70.0)
    assert res_hot.flag == SensorQualityFlag.SUSPECT_HIGH
    assert res_hot.is_valid_for_model is True


def test_missing_and_non_finite_values():
    """Verify missing, empty string, non-numeric, NaN, and Inf are classified as MISSING."""
    for bad in [None, "", "   ", "abc", float("nan"), float("inf"), float("-inf"), True, False]:
        res = validate_parameter("pH", bad)
        assert res.flag == SensorQualityFlag.MISSING
        assert res.is_valid_for_model is False
        assert res.is_valid_for_alerts is False


def test_oci_definition_and_missing_semantics():
    """Verify OCI range [0.0, 1.0] and ensure missing OCI is never implicitly coerced to 0.0."""
    # Valid range
    assert validate_parameter("optical_colour_index", 0.0).flag == SensorQualityFlag.VALID
    assert validate_parameter("optical_colour_index", 0.75).flag == SensorQualityFlag.VALID
    assert validate_parameter("optical_colour_index", 1.0).flag == SensorQualityFlag.VALID

    # Out of bounds
    assert validate_parameter("optical_colour_index", -0.1).flag == SensorQualityFlag.OUT_OF_BOUNDS
    assert validate_parameter("optical_colour_index", 1.5).flag == SensorQualityFlag.OUT_OF_BOUNDS

    # Missing value is None, never 0.0
    res_none = validate_parameter("optical_colour_index", None)
    assert res_none.flag == SensorQualityFlag.MISSING
    assert res_none.coerced_value is None
    assert coerce_model_parameter("optical_colour_index", None) is None


# ---------------------------------------------------------------------------
# Part 2: Alerts & Auto-Resolution Guards
# ---------------------------------------------------------------------------

def test_invalid_readings_do_not_resolve_active_alerts():
    """Verify that dropouts (TDS=0.0, pH=0.0, Temp=0.0) cannot resolve active alerts."""
    node_id = "test_node_alert_resolve"
    now = datetime.now(timezone.utc)

    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Test Node", "Lab")
        # Create an active TDS alert (> 500)
        AlertRepository.create(
            db=db,
            node_id=node_id,
            timestamp=now - timedelta(minutes=10),
            parameter="TDS",
            value=650.0,
            threshold=500.0,
            severity="WARNING",
            message="TDS above threshold",
            status="ACTIVE",
        )
        # Create an active pH alert (< 6.5)
        AlertRepository.create(
            db=db,
            node_id=node_id,
            timestamp=now - timedelta(minutes=10),
            parameter="pH",
            value=5.8,
            threshold=6.5,
            severity="WARNING",
            message="pH below threshold",
            status="ACTIVE",
        )

    # Attempt to resolve with TDS = 0.0 (sensor dropout)
    with get_db_context() as db:
        resolved = AlertService.check_and_resolve_alerts(
            db=db,
            node_id=node_id,
            reading_data={"timestamp": now, "tds": 0.0},
        )
        assert resolved == 0  # TDS=0.0 is a dropout; cannot resolve alert!

        # Attempt to resolve with pH = 0.0 (sensor dropout)
        resolved_ph = AlertService.check_and_resolve_alerts(
            db=db,
            node_id=node_id,
            reading_data={"timestamp": now, "ph": 0.0},
        )
        assert resolved_ph == 0

        # Attempt to resolve with negative TDS (-20.0)
        resolved_neg = AlertService.check_and_resolve_alerts(
            db=db,
            node_id=node_id,
            reading_data={"timestamp": now, "tds": -20.0},
        )
        assert resolved_neg == 0

        # Confirm alerts are still ACTIVE
        active_alerts = AlertRepository.get_active_by_node(db, node_id)
        assert len(active_alerts) == 2

    # Now provide a genuinely normal reading (TDS = 300.0, pH = 7.2)
    with get_db_context() as db:
        resolved_valid = AlertService.check_and_resolve_alerts(
            db=db,
            node_id=node_id,
            reading_data={"timestamp": now, "tds": 300.0, "ph": 7.2},
        )
        assert resolved_valid == 2

        active_remaining = AlertRepository.get_active_by_node(db, node_id)
        assert len(active_remaining) == 0


def test_sensor_dropouts_do_not_generate_false_alerts():
    """Verify that 0V probe dropouts (pH=0.0) do not trigger false 'low pH' alerts."""
    node_id = "test_node_no_false_alert"
    now = datetime.now(timezone.utc)

    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Test Node", "Lab")
        # pH = 0.0 is a dropout; should not trigger an alert despite being < 6.5
        alerts = AlertService.evaluate_reading_for_alerts(
            db=db,
            node_id=node_id,
            reading_data={"timestamp": now, "ph": 0.0, "tds": 0.0},
        )
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Part 3: Ingestion, Chronological Ordering & Model Window Gap-Filling
# ---------------------------------------------------------------------------

def test_feed_sorting_and_chronological_ordering():
    """Verify feeds are strictly sorted ascending by timestamp and entry_id."""
    f1 = {"created_at": "2026-10-20T10:00:00Z", "entry_id": 1}
    f2 = {"created_at": "2026-10-20T11:00:00Z", "entry_id": 2}
    f3 = {"created_at": "2026-10-20T12:00:00Z", "entry_id": 3}

    unordered = [f3, f1, f2]
    ordered = sorted(unordered, key=_feed_sort_key)
    assert ordered == [f1, f2, f3]


def test_model_window_never_receives_dropouts_or_zeros():
    """Verify that dropouts (pH=0, TDS=0) in feeds become missing and are causally filled."""
    config = ThingSpeakConfig(channel_id="999", results=3)
    feeds = [
        {"created_at": "2026-10-20T10:00:00Z", "entry_id": 1, "field1": "7.2", "field2": "200.0", "field3": "1.0", "field4": "25.0"},
        {"created_at": "2026-10-20T11:00:00Z", "entry_id": 2, "field1": "0.0", "field2": "0.0", "field3": "-1.0", "field4": "0.0"},  # all dropouts/invalid
        {"created_at": "2026-10-20T12:00:00Z", "entry_id": 3, "field1": "7.4", "field2": "210.0", "field3": "1.2", "field4": "26.0"},
    ]

    window = parse_feeds(feeds, config)

    # In row 1 (the dropout row), values must be filled causally from row 0 (200.0, 7.2, 1.0, 25.0),
    # NEVER 0.0 or negative values!
    row1 = window.values[1]
    assert row1[0] == pytest.approx(7.2)   # pH carried forward
    assert row1[1] == pytest.approx(200.0) # TDS carried forward, NOT 0.0
    assert row1[2] == pytest.approx(1.0)   # Turbidity carried forward, NOT -1.0
    assert row1[3] == pytest.approx(25.0)  # Temp carried forward, NOT 0.0


def test_raw_rgb_fields_preserved_display_only():
    """Verify raw RGB channels (fields 5-7) are extracted for UI but excluded from ML values."""
    config = ThingSpeakConfig(channel_id="999", results=1)
    feeds = [
        {
            "created_at": "2026-10-20T10:00:00Z",
            "entry_id": 1,
            "field1": "7.2",
            "field2": "200.0",
            "field3": "1.0",
            "field4": "25.0",
            "field5": "45",  # red
            "field6": "50",  # green
            "field7": "55",  # blue
        }
    ]

    window = parse_feeds(feeds, config)
    assert window.values[0] == (7.2, 200.0, 1.0, 25.0)  # Exactly 4 ML features
    assert len(window.values[0]) == 4                   # RGB is NOT in model feature array
    assert window.rgb_values[0] == (45, 50, 55, None)   # RGB preserved separately
