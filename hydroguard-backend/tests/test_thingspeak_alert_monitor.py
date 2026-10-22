"""Tests for continuous ThingSpeak alert monitoring service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth import authenticated_principal, require_student_or_admin
from app.db.database import get_db_context, init_db
from app.db.models import Alert
from app.db.repositories import (
    AlertRepository,
    NodeRepository,
    ThingSpeakMonitorRepository,
    ThresholdRepository,
)
from app.main import app
from app.services.alert_service import AlertService
from app.services.thingspeak_alert_monitor import (
    ThingSpeakAlertMonitor,
    _is_new_feed,
    _resolve_poll_interval,
    get_alert_monitor,
)
from ml.services import thingspeak_service as ts
from ml.services.thingspeak_service import (
    ThingSpeakConfig,
    ThingSpeakUnavailable,
)


def _feed(
    entry_id: int,
    hour: int = 12,
    ph: str = "7.20",
    tds: str = "200.0",
    turb: str = "1.5",
    temp: str = "24.0",
    r: str = "45",
    g: str = "50",
    b: str = "55",
    status: str = "0",
) -> dict:
    return {
        "created_at": f"2026-10-18T{hour:02d}:00:00Z",
        "entry_id": entry_id,
        "field1": ph,
        "field2": tds,
        "field3": turb,
        "field4": temp,
        "field5": r,
        "field6": g,
        "field7": b,
        "field8": status,
    }


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()
    with get_db_context() as db:
        from app.db.models import Alert, ThingSpeakMonitorCheckpoint, ThresholdConfig
        db.query(Alert).filter(Alert.node_id.like("thingspeak-%")).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()
    yield
    with get_db_context() as db:
        from app.db.models import Alert, ThingSpeakMonitorCheckpoint, ThresholdConfig
        db.query(Alert).filter(Alert.node_id.like("thingspeak-%")).delete()
        db.query(ThingSpeakMonitorCheckpoint).delete()
        db.query(ThresholdConfig).delete()
        db.commit()



@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_student_or_admin,
        lambda: {"uid": "test-student", "role": "STUDENT"},
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "test-student", "role": "STUDENT"},
    )
    yield TestClient(app)
    app.dependency_overrides.pop(require_student_or_admin, None)
    app.dependency_overrides.pop(authenticated_principal, None)


# ---------------------------------------------------------------------------
# Test 1 & 2: Lifespan start and clean stop
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_monitor_starts_and_stops_with_lifespan(monkeypatch):
    """Monitor starts on lifespan startup when configured and stops on shutdown."""
    monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "11101")
    monkeypatch.setenv("HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS", "1.0")

    monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: [_feed(1)])

    monitor = get_alert_monitor()
    # Ensure fresh state
    await monitor.stop()

    assert not monitor.is_running
    started = await monitor.start()
    assert started is True
    assert monitor.is_running

    await monitor.stop()
    assert not monitor.is_running


# ---------------------------------------------------------------------------
# Test 3: Unconfigured channel does not prevent startup
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_unconfigured_channel_does_not_prevent_startup(monkeypatch):
    """Unconfigured channel logs warning and disables monitor; app still starts."""
    monkeypatch.delenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", raising=False)

    monitor = ThingSpeakAlertMonitor()
    started = await monitor.start()
    assert started is False
    assert not monitor.is_running

    # Verify FastAPI endpoints still respond
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 4: Threshold breach creates alert without calling Forecast endpoint
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_violating_feed_creates_alert_without_forecast(monkeypatch):
    """A valid new feed that breaches a threshold creates an alert without calling forecast."""
    channel_id = "11104"
    node_id = f"thingspeak-{channel_id}"

    # pH = 6.0 (below default min 6.5)
    feeds = [_feed(entry_id=1, ph="6.0")]

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: feeds,
    )

    with get_db_context() as db:
        before = db.query(Alert).filter(Alert.node_id == node_id).count()

    # Poll directly without touching /thingspeak/forecast
    processed = await monitor.poll_once()
    assert processed == 1

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == before + 1
        created = alerts[-1]
        assert created.parameter == "pH"
        assert created.status == "ACTIVE"
        assert created.severity == "WARNING"
        assert float(created.value) == 6.0
        assert float(created.threshold) == 6.5


# ---------------------------------------------------------------------------
# Test 5: Normal feed resolves existing alert
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_normal_feed_resolves_existing_alert():
    """When a subsequent feed returns to normal, the active alert is auto-resolved."""
    channel_id = "11105"
    node_id = f"thingspeak-{channel_id}"

    store = {"feeds": [_feed(entry_id=1, ph="6.0")]}
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: store["feeds"],
    )

    # First poll: creates active alert
    await monitor.poll_once()

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 1
        assert alerts[0].status == "ACTIVE"
        alert_id = alerts[0].id

    # Second poll: normal feed arrives
    store["feeds"] = [_feed(entry_id=1, ph="6.0"), _feed(entry_id=2, ph="7.2")]
    await monitor.poll_once()

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 1
        assert alerts[0].id == alert_id
        assert alerts[0].status == "RESOLVED"


# ---------------------------------------------------------------------------
# Test 6: Repeated polling of same feed does not duplicate alerts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_repeated_polling_no_duplicate_alerts():
    """Repeated polling of the exact same feed creates only 1 alert."""
    channel_id = "11106"
    node_id = f"thingspeak-{channel_id}"
    feeds = [_feed(entry_id=10, ph="6.0")]

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: feeds,
    )

    # Poll 1
    p1 = await monitor.poll_once()
    assert p1 == 1

    # Poll 2 (same feeds)
    p2 = await monitor.poll_once()
    assert p2 == 0

    # Poll 3 (same feeds)
    p3 = await monitor.poll_once()
    assert p3 == 0

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# Test 7: Several new feeds processed in chronological order
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_several_feeds_processed_chronologically():
    """Several feeds arriving in a batch are evaluated oldest-first."""
    channel_id = "11107"
    node_id = f"thingspeak-{channel_id}"

    # Feed 1 (10:00): pH violation
    f1 = _feed(entry_id=1, hour=10, ph="6.0", tds="200.0")
    # Feed 2 (11:00): pH returns to normal (resolves pH alert)
    f2 = _feed(entry_id=2, hour=11, ph="7.0", tds="200.0")
    # Feed 3 (12:00): TDS violation (> 500)
    f3 = _feed(entry_id=3, hour=12, ph="7.0", tds="600.0")

    # Present them out-of-order in the mock to test chronological sorting
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [f2, f3, f1],
    )

    processed = await monitor.poll_once()
    assert processed == 3

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).order_by(Alert.id.asc()).all()
        assert len(alerts) == 2

        ph_alert = next(a for a in alerts if a.parameter == "pH")
        tds_alert = next(a for a in alerts if a.parameter == "TDS")

        assert ph_alert.status == "RESOLVED"
        assert tds_alert.status == "ACTIVE"


# ---------------------------------------------------------------------------
# Test 8 & 13: Restarting monitor does not duplicate alerts (checkpoint persistence)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_restarting_monitor_preserves_checkpoint_no_duplicate_alerts():
    """Checkpoint persistence across monitor instances prevents duplicate alerts."""
    channel_id = "11108"
    node_id = f"thingspeak-{channel_id}"
    feeds = [_feed(entry_id=5, ph="6.0")]

    # Monitor instance 1
    m1 = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: feeds,
    )
    assert await m1.poll_once() == 1

    with get_db_context() as db:
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        assert cp is not None
        assert cp.last_entry_id == 5
        count1 = db.query(Alert).filter(Alert.node_id == node_id).count()
        assert count1 == 1

    # Monitor instance 2 (simulating fresh application restart)
    m2 = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: feeds,
    )
    assert await m2.poll_once() == 0

    with get_db_context() as db:
        count2 = db.query(Alert).filter(Alert.node_id == node_id).count()
        assert count2 == 1


# ---------------------------------------------------------------------------
# Test 9: ThingSpeak outage does not crash monitor; recovers when reachable
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_thingspeak_outage_resumes_on_recovery():
    """ThingSpeak failures do not crash monitor; subsequent successful poll processes feeds."""
    channel_id = "11109"
    node_id = f"thingspeak-{channel_id}"

    state = {"fail": True}

    def _flaky_fetch(config, client=None):
        if state["fail"]:
            raise ThingSpeakUnavailable("ThingSpeak API timeout")
        return [_feed(entry_id=1, ph="6.0")]

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=_flaky_fetch,
    )

    # First poll raises ThingSpeakUnavailable
    with pytest.raises(ThingSpeakUnavailable):
        await monitor.poll_once()

    # Recovery
    state["fail"] = False
    processed = await monitor.poll_once()
    assert processed == 1

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# Test 10: Invalid readings are ignored safely
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_invalid_readings_ignored_safely():
    """Invalid, empty, or unparseable values produce no alerts and do not crash."""
    channel_id = "11110"
    node_id = f"thingspeak-{channel_id}"

    invalid_feed = {
        "created_at": "2026-10-18T12:00:00Z",
        "entry_id": 1,
        "field1": "not-numeric",
        "field2": "",
        "field3": "99999999",  # Out of physical bounds
        "field4": None,
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [invalid_feed],
    )

    processed = await monitor.poll_once()
    assert processed == 1  # Feed inspected and checkpoint updated

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Test 11: RGB-only changes do not generate colour alerts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rgb_changes_do_not_generate_colour_alerts():
    """RGB values on fields 5-7 never generate alerts or optical colour index alerts."""
    channel_id = "11111"
    node_id = f"thingspeak-{channel_id}"

    rgb_feed = _feed(
        entry_id=1,
        ph="7.2",
        tds="200.0",
        turb="1.0",
        temp="22.0",
        r="99",
        g="99",
        b="99",
    )

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [rgb_feed],
    )

    await monitor.poll_once()

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Test 12: Admin-configured thresholds are honored
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_admin_configured_thresholds_honored():
    """Admin-updated thresholds are used rather than default thresholds."""
    channel_id = "11112"
    node_id = f"thingspeak-{channel_id}"

    # Set custom TDS max threshold to 250.0 (default is 500.0)
    with get_db_context() as db:
        ThresholdRepository.upsert(db, "tds", min_value=None, max_value=250.0)

    # TDS is 300.0 (below default 500, but above custom 250)
    feeds = [_feed(entry_id=1, tds="300.0")]

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: feeds,
    )

    await monitor.poll_once()

    with get_db_context() as db:
        alerts = db.query(Alert).filter(Alert.node_id == node_id).all()
        assert len(alerts) == 1
        assert alerts[0].parameter == "TDS"
        assert float(alerts[0].threshold) == 250.0
        assert float(alerts[0].value) == 300.0


# ---------------------------------------------------------------------------
# Test 14: Database sessions close properly on success and error
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_database_sessions_close_cleanly(monkeypatch):
    """Database sessions are always closed even if evaluation raises an unexpected error."""
    channel_id = "11114"

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [_feed(1, ph="6.0")],
    )

    def _exploding_evaluate(*args, **kwargs):
        raise RuntimeError("Simulated DB crash during alert evaluation")

    monkeypatch.setattr(AlertService, "evaluate_reading_for_alerts", _exploding_evaluate)

    with pytest.raises(RuntimeError, match="Simulated DB crash"):
        await monitor.poll_once()

    # Verify connection was released and next operation works
    with get_db_context() as db:
        cp = ThingSpeakMonitorRepository.get_checkpoint(db, channel_id)
        # Checkpoint was not advanced because transaction rolled back
        assert cp is None or cp.last_entry_id is None


# ---------------------------------------------------------------------------
# Test 15: Multi-worker coordination and preventing duplicate monitors
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_lease_coordination_and_prevent_duplicate_monitors():
    """Lease coordination prevents concurrent workers from processing the same feeds."""
    channel_id = "11115"

    m1 = ThingSpeakAlertMonitor(config=ThingSpeakConfig(channel_id=channel_id))
    m2 = ThingSpeakAlertMonitor(config=ThingSpeakConfig(channel_id=channel_id))

    with get_db_context() as db:
        # Worker 1 acquires lease
        acq1 = ThingSpeakMonitorRepository.acquire_lease(db, channel_id, m1._worker_id, lease_seconds=60)
        assert acq1 is True

        # Worker 2 attempts to acquire lease simultaneously -> rejected
        acq2 = ThingSpeakMonitorRepository.acquire_lease(db, channel_id, m2._worker_id, lease_seconds=60)
        assert acq2 is False

        # Worker 1 releases lease
        ThingSpeakMonitorRepository.release_lease(db, channel_id, m1._worker_id)

        # Worker 2 can now acquire lease
        acq2_retry = ThingSpeakMonitorRepository.acquire_lease(db, channel_id, m2._worker_id, lease_seconds=60)
        assert acq2_retry is True
        ThingSpeakMonitorRepository.release_lease(db, channel_id, m2._worker_id)


# ---------------------------------------------------------------------------
# Polling interval validation
# ---------------------------------------------------------------------------

def test_polling_interval_validation(monkeypatch):
    """Polling interval parsing handles missing, invalid, negative, and clamped values."""
    assert _resolve_poll_interval({}) == 30.0
    assert _resolve_poll_interval({"HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS": "45.5"}) == 45.5
    assert _resolve_poll_interval({"HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS": "0"}) == 30.0
    assert _resolve_poll_interval({"HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS": "-10"}) == 30.0
    assert _resolve_poll_interval({"HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS": "not-a-number"}) == 30.0
    assert _resolve_poll_interval({"HYDROGUARD_THINGSPEAK_ALERT_POLL_SECONDS": "0.01"}) == 0.1


# ---------------------------------------------------------------------------
# Android App compatibility test: GET /api/v1/nodes/{node_id}/alerts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_android_api_can_retrieve_monitor_generated_alert(auth_client):
    """The existing Android alerts API endpoint retrieves alerts generated by the monitor."""
    channel_id = "11117"
    node_id = f"thingspeak-{channel_id}"

    # Generate an alert via monitor
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [_feed(entry_id=1, ph="6.0")],
    )
    await monitor.poll_once()

    # Call existing alerts endpoint used by the Android app
    resp = auth_client.get(f"/api/v1/nodes/{node_id}/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    alert = data["alerts"][0]
    assert alert["node_id"] == node_id
    assert alert["parameter"] == "pH"
    assert alert["status"] == "ACTIVE"


# ---------------------------------------------------------------------------
# Regression Tests: Android Water Screen & ThingSpeak Alert Integration
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ph_and_turbidity_breaches_generate_visible_alerts_for_thingspeak(auth_client):
    """Live readings matching observed values (pH 12.41, turbidity 29.08) generate active alerts."""
    channel_id = "244357"
    node_id = f"thingspeak-{channel_id}"

    # Observed reading from live channel: pH 12.41, TDS 5.47, Turbidity 29.08, Temp 25.56
    feed = {
        "created_at": "2026-10-18T12:00:00Z",
        "entry_id": 100,
        "field1": "12.41",
        "field2": "5.47",
        "field3": "29.08",
        "field4": "25.56",
        "field5": "40",
        "field6": "29",
        "field7": "30",
        "field8": "0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    # Query alerts for the ThingSpeak node
    resp = auth_client.get(f"/api/v1/nodes/{node_id}/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    params = {a["parameter"]: a for a in data["alerts"]}
    assert "pH" in params
    assert params["pH"]["status"] == "ACTIVE"
    assert float(params["pH"]["value"]) == 12.41
    assert "turbidity" in params
    assert params["turbidity"]["status"] == "ACTIVE"
    assert float(params["turbidity"]["value"]) == 29.08


@pytest.mark.anyio
async def test_thingspeak_alerts_independent_of_other_nodes(auth_client):
    """ThingSpeak alerts are isolated to thingspeak-{channel_id} and other nodes remain independent."""
    channel_id = "244357"
    ts_node_id = f"thingspeak-{channel_id}"
    other_node_id = "node_overhead_a"

    # Create an alert on node_overhead_a manually via database
    with get_db_context() as db:
        NodeRepository.get_or_create(db, other_node_id, name="Overhead Tank A", location="Hostel", status="offline")
        AlertRepository.create(
            db=db,
            node_id=other_node_id,
            timestamp=datetime.now(timezone.utc),
            parameter="pH",
            value=6.2,
            threshold=6.5,
            severity="WARNING",
            message="pH below threshold on Overhead Tank A",
        )

    # Create ThingSpeak alerts via monitor
    feed = {
        "created_at": "2026-10-18T12:01:00Z",
        "entry_id": 101,
        "field1": "12.41",
        "field2": "5.47",
        "field3": "29.08",
        "field4": "25.56",
        "field5": "40",
        "field6": "29",
        "field7": "30",
        "field8": "0",
    }
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    # Querying thingspeak node returns only thingspeak alerts
    ts_resp = auth_client.get(f"/api/v1/nodes/{ts_node_id}/alerts")
    assert ts_resp.status_code == 200
    ts_alerts = ts_resp.json()["alerts"]
    for a in ts_alerts:
        assert a["node_id"] == ts_node_id

    # Querying node_overhead_a returns only node_overhead_a alerts
    other_resp = auth_client.get(f"/api/v1/nodes/{other_node_id}/alerts")
    assert other_resp.status_code == 200
    other_alerts = other_resp.json()["alerts"]
    assert len(other_alerts) == 1
    assert other_alerts[0]["node_id"] == other_node_id
    assert float(other_alerts[0]["value"]) == 6.2


@pytest.mark.anyio
async def test_sensor_dropouts_cannot_create_or_resolve_alerts(auth_client):
    """0V ADC sensor dropouts (e.g. pH 0.0, temp 0.0) cannot trigger false alerts or falsely resolve active alerts."""
    channel_id = "244357"
    node_id = f"thingspeak-{channel_id}"

    # Step 1: Create active alerts with violating feed
    violating_feed = {
        "created_at": "2026-10-18T12:00:00Z",
        "entry_id": 102,
        "field1": "12.41",
        "field2": "5.47",
        "field3": "29.08",
        "field4": "25.56",
        "field5": "40",
        "field6": "29",
        "field7": "30",
        "field8": "0",
    }
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [violating_feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        active_before = AlertRepository.get_active_by_node(db, node_id)
        assert len(active_before) == 2

    # Step 2: Feed with 0V probe dropout (pH 0.00, temp 0.00, turbidity 0.00)
    # Even though 0.00 is <= max threshold 8.5 for pH and 5.0 for turbidity,
    # pH 0.00 is physically invalid and must NOT falsely resolve the pH alert.
    dropout_feed = {
        "created_at": "2026-10-18T12:00:25Z",
        "entry_id": 103,
        "field1": "0.00",
        "field2": "5.47",
        "field3": "0.00",
        "field4": "0.00",
        "field5": "0",
        "field6": "0",
        "field7": "0",
        "field8": "0",
    }
    monitor._fetch_feeds_fn = lambda config, client=None: [dropout_feed]
    await monitor.poll_once()

    # pH alert must still be ACTIVE, not resolved by sensor dropout
    with get_db_context() as db:
        active_after = AlertRepository.get_active_by_node(db, node_id)
        active_params = {a.parameter: a for a in active_after}
        assert "pH" in active_params
        assert active_params["pH"].status == "ACTIVE"


@pytest.mark.anyio
async def test_stale_or_simulated_readings_cannot_resolve_alerts():
    """Stale timestamp or simulated data sources cannot falsely resolve real ThingSpeak alerts."""
    channel_id = "244357"
    node_id = f"thingspeak-{channel_id}"

    alert_time = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, name="ThingSpeak Node", location="Hostel", status="online")
        AlertRepository.create(
            db=db,
            node_id=node_id,
            timestamp=alert_time,
            parameter="pH",
            value=12.41,
            threshold=8.5,
            severity="WARNING",
            message="pH violation",
        )

    # 1. Stale reading (timestamp before alert_time)
    with get_db_context() as db:
        stale_reading = {
            "node_id": node_id,
            "timestamp": datetime(2026, 10, 18, 11, 55, 0, tzinfo=timezone.utc),
            "ph": 7.2,
            "source": "THINGSPEAK",
        }
        resolved = AlertService.check_and_resolve_alerts(db, node_id, stale_reading)
        assert resolved == 0
        active = AlertRepository.get_active_by_node(db, node_id)
        assert len(active) == 1

    # 2. Simulated reading (source is SIMULATED_DEVELOPMENT)
    with get_db_context() as db:
        simulated_reading = {
            "node_id": node_id,
            "timestamp": datetime(2026, 10, 18, 12, 5, 0, tzinfo=timezone.utc),
            "ph": 7.2,
            "source": "SIMULATED_DEVELOPMENT",
        }
        resolved = AlertService.check_and_resolve_alerts(db, node_id, simulated_reading)
        assert resolved == 0
        active = AlertRepository.get_active_by_node(db, node_id)
        assert len(active) == 1


@pytest.mark.anyio
async def test_normal_subsequent_reading_resolves_alert(auth_client):
    """Genuinely normal subsequent ThingSpeak reading resolves the active alert."""
    channel_id = "244357"
    node_id = f"thingspeak-{channel_id}"

    # Step 1: Create active alerts
    v_feed = {
        "created_at": "2026-10-18T12:00:00Z",
        "entry_id": 104,
        "field1": "12.41",
        "field2": "5.47",
        "field3": "29.08",
        "field4": "25.56",
        "field5": "40",
        "field6": "29",
        "field7": "30",
        "field8": "0",
    }
    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [v_feed],
    )
    await monitor.poll_once()

    with get_db_context() as db:
        active = AlertRepository.get_active_by_node(db, node_id)
        assert len(active) == 2

    # Step 2: Feed with normal water quality
    normal_feed = {
        "created_at": "2026-10-18T12:01:00Z",
        "entry_id": 105,
        "field1": "7.35",
        "field2": "150.0",
        "field3": "1.20",
        "field4": "24.50",
        "field5": "40",
        "field6": "30",
        "field7": "30",
        "field8": "0",
    }
    monitor._fetch_feeds_fn = lambda config, client=None: [normal_feed]
    await monitor.poll_once()

    # Verify both alerts are now RESOLVED
    resp = auth_client.get(f"/api/v1/nodes/{node_id}/alerts")
    assert resp.status_code == 200
    alerts = resp.json()["alerts"]
    for a in alerts:
        assert a["status"] == "RESOLVED"


def test_thingspeak_latest_endpoint_includes_provenance_node_and_channel(auth_client, monkeypatch):
    """GET /api/v1/thingspeak/latest returns channel_id and node_id in response."""
    monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")
    monkeypatch.setattr(
        ts,
        "fetch_feeds",
        lambda config, client=None: [_feed(entry_id=200, ph="7.20")],
    )
    resp = auth_client.get("/api/v1/thingspeak/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert "channel_id" in data
    assert data["channel_id"] == "244357"
    assert "node_id" in data
    assert data["node_id"] == "thingspeak-244357"



@pytest.mark.anyio
async def test_thingspeak_feed_persists_to_database_and_deduplicates(auth_client):
    """ThingSpeak readings are persisted into SensorReading table and deduplicated on re-poll."""
    from app.db.repositories import SensorReadingRepository
    from datetime import datetime, timezone

    channel_id = "11120"
    node_id = f"thingspeak-{channel_id}"
    feed_ts = datetime(2026, 10, 18, 12, 10, 0, tzinfo=timezone.utc)

    feed = {
        "created_at": "2026-10-18T12:10:00Z",
        "entry_id": 501,
        "field1": "7.45",
        "field2": "120.5",
        "field3": "1.85",
        "field4": "26.10",
        "field5": "42",
        "field6": "28",
        "field7": "30",
        "field8": "0",
    }

    monitor = ThingSpeakAlertMonitor(
        config=ThingSpeakConfig(channel_id=channel_id),
        fetch_feeds_fn=lambda config, client=None: [feed],
    )
    await monitor.poll_once()

    # 1. Verify reading is persisted in SensorReading table
    with get_db_context() as db:
        reading = SensorReadingRepository.get_by_node_and_timestamp(db, node_id, feed_ts)
        assert reading is not None
        assert float(reading.ph) == 7.45
        assert float(reading.tds) == 120.5
        assert float(reading.turbidity) == 1.85
        assert float(reading.temperature) == 26.10
        assert reading.red == 42
        assert reading.green == 28
        assert reading.blue == 30
        assert reading.source == "THINGSPEAK"

        count_before = SensorReadingRepository.get_count_by_node(db, node_id)
        assert count_before >= 1

    # 2. Verify reading is returned by history endpoint
    resp = auth_client.get(f"/api/v1/nodes/{node_id}/readings/history")
    assert resp.status_code == 200
    history = resp.json()["readings"]
    matching = [r for r in history if r["timestamp"].startswith("2026-10-18T12:10:00")]
    assert len(matching) == 1
    assert matching[0]["source"] == "REAL_SENSOR"

    # 3. Poll same feed again (deduplication check)
    await monitor.poll_once()

    with get_db_context() as db:
        count_after = SensorReadingRepository.get_count_by_node(db, node_id)
        assert count_after == count_before
