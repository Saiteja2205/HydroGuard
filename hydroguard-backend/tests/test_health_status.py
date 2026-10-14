"""Health must report evidence, not constants.

The pre-existing endpoint returned a fixed ``sensors_connected=False`` and three
fixed ``False`` model flags from a handler with no dependencies at all. That was
honest only by coincidence: it could not tell "no hardware attached" apart from
"the database is down", and it could not become honest once real sensors arrive.

These tests pin the new contract:

* the API still answers 200 while only claiming liveness;
* database, model, sensor-ingestion and freshness states are triaged separately;
* simulated/historical rows NEVER make the API claim connected sensors;
* a slow or broken database degrades one field instead of hanging the probe;
* no stack traces or filesystem paths leak into a public response.

Isolation note: the suite shares one throwaway database across every test file.
Tests here therefore either scope their rows to a dedicated node, or drive the
triage helpers directly, so they stay correct regardless of the order pytest
runs the files in and never delete another module's fixtures.
"""

import sys
import time
import types
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db_context, init_db
from app.db.models import Node, SensorReading

NODE_ID = "health_node"


@pytest.fixture(autouse=True, scope="module")
def _database():
    init_db()


def _client() -> TestClient:
    from app.main import app

    return TestClient(app)


def _add_reading(source: str, when: datetime) -> None:
    """Add one reading for this module's own node, leaving other data alone."""
    with get_db_context() as db:
        if db.query(Node).filter_by(node_id=NODE_ID).first() is None:
            db.add(Node(node_id=NODE_ID, name="Health node", location="Test", status="online"))
            db.commit()
        db.add(
            SensorReading(
                node_id=NODE_ID,
                timestamp=when,
                ph=7.0,
                tds=120.0,
                turbidity=1.5,
                temperature=25.0,
                source=source,
            )
        )
        db.commit()


def _use_latest(monkeypatch, observed, live):
    """Drive the health module's own queries, so state tests are order-proof."""
    from app.api import health as health_module

    monkeypatch.setattr(health_module, "_latest_observation", lambda db: observed)
    monkeypatch.setattr(health_module, "_latest_live_observation", lambda db: live)


# ---------------------------------------------------------------------------
# Liveness and backward compatibility
# ---------------------------------------------------------------------------


def test_health_reports_ok_and_still_returns_every_pre_existing_field():
    """The response shape must not break clients written against aed6172."""
    response = _client().get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "HydroGuard ML API"
    assert body["version"] == "1.0.0"
    assert isinstance(body["sensors_connected"], bool)
    assert set(body["models_loaded"]) == {"lstm", "patchtst", "timemixer"}
    assert body["data_mode"] == "historical_or_simulated"


def test_checked_at_is_a_timezone_aware_utc_timestamp():
    body = _client().get("/api/v1/health").json()
    parsed = datetime.fromisoformat(body["checked_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 300


def test_every_triage_dimension_is_present_and_reported_separately():
    body = _client().get("/api/v1/health").json()
    assert body["database"]["state"] in {"ok", "unavailable"}
    assert body["models"]["state"] in {"loaded", "not_loaded", "unavailable"}
    assert body["sensor_ingestion"]["state"] in {"recent", "stale", "not_configured"}
    assert body["data_freshness"]["state"] in {"fresh", "stale", "empty"}


def test_health_stays_reachable_without_any_credentials():
    """Liveness probes cannot authenticate, so health must not require it."""
    response = _client().get("/api/v1/health")
    assert response.status_code == 200
    assert "authorization" not in {key.lower() for key in response.request.headers}


# ---------------------------------------------------------------------------
# Sensor connectivity must never be inferred from stored rows
# ---------------------------------------------------------------------------


def test_simulated_rows_never_produce_a_connected_sensors_claim(monkeypatch):
    """The core honesty requirement: simulated data is not hardware evidence."""
    now = datetime.now(timezone.utc)
    # A recent simulated row exists, but no LIVE provenance has ever arrived.
    _use_latest(monkeypatch, observed=(now - timedelta(seconds=5), "SIMULATED_DEVELOPMENT"), live=None)

    body = _client().get("/api/v1/health").json()

    assert body["sensors_connected"] is False
    assert body["sensor_ingestion"]["state"] == "not_configured"
    assert body["sensor_ingestion"]["last_real_sensor_at"] is None
    assert "REAL_SENSOR" in body["sensor_ingestion"]["detail"]


def test_sensor_ingestion_reports_not_configured_end_to_end_through_the_database(monkeypatch):
    """Real rows for this node, with no LIVE provenance anywhere in scope."""
    from app.api import health as health_module

    _add_reading("SIMULATED_DEVELOPMENT", datetime.now(timezone.utc))
    # Scope the LIVE query to "no REAL_SENSOR rows", which is the deployed truth.
    monkeypatch.setattr(health_module, "_latest_live_observation", lambda db: None)

    body = _client().get("/api/v1/health").json()

    assert body["sensor_ingestion"]["state"] == "not_configured"
    assert body["sensors_connected"] is False


def test_recent_real_sensor_observation_reports_a_live_heartbeat():
    """Newest LIVE row wins, so this assertion holds whatever else is stored."""
    _add_reading("REAL_SENSOR", datetime.now(timezone.utc) - timedelta(seconds=30))

    body = _client().get("/api/v1/health").json()

    assert body["sensor_ingestion"]["state"] == "recent"
    assert body["sensors_connected"] is True
    assert body["sensor_ingestion"]["last_real_sensor_at"] is not None
    assert body["sensor_ingestion"]["age_seconds"] < 60


def test_old_live_observation_is_stale_and_does_not_claim_connection(monkeypatch):
    """Provenance alone is not a heartbeat; recency is required too."""
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    _use_latest(monkeypatch, observed=(stale, "REAL_SENSOR"), live=stale)

    body = _client().get("/api/v1/health").json()

    assert body["sensor_ingestion"]["state"] == "stale"
    assert body["sensors_connected"] is False
    assert body["sensor_ingestion"]["age_seconds"] >= 6 * 3600
    assert body["sensor_ingestion"]["detail"]


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------


def test_freshness_reports_empty_when_nothing_is_stored(monkeypatch):
    _use_latest(monkeypatch, observed=None, live=None)

    body = _client().get("/api/v1/health").json()

    assert body["data_freshness"]["state"] == "empty"
    assert body["data_freshness"]["latest_observed_at"] is None
    assert body["data_freshness"]["source"] is None


def test_freshness_reports_fresh_with_the_observation_provenance(monkeypatch):
    when = datetime.now(timezone.utc) - timedelta(minutes=2)
    _use_latest(monkeypatch, observed=(when, "SIMULATED_DEVELOPMENT"), live=None)

    body = _client().get("/api/v1/health").json()

    assert body["data_freshness"]["state"] == "fresh"
    assert body["data_freshness"]["source"] == "SIMULATED_DEVELOPMENT"
    assert body["data_freshness"]["latest_observed_at"] is not None
    assert 0 <= body["data_freshness"]["age_seconds"] < 360


def test_freshness_reports_stale_for_an_old_observation(monkeypatch):
    when = datetime.now(timezone.utc) - timedelta(days=3)
    _use_latest(monkeypatch, observed=(when, "HISTORICAL_DATA"), live=None)

    body = _client().get("/api/v1/health").json()

    assert body["data_freshness"]["state"] == "stale"
    assert body["data_freshness"]["age_seconds"] >= 3 * 86400
    assert body["data_freshness"]["detail"]


def test_future_dated_rows_never_report_a_negative_age(monkeypatch):
    """The reading contract tolerates modest clock skew, so clamp, don't crash."""
    when = datetime.now(timezone.utc) + timedelta(minutes=10)
    _use_latest(monkeypatch, observed=(when, "SIMULATED_DEVELOPMENT"), live=None)

    body = _client().get("/api/v1/health").json()

    assert body["data_freshness"]["age_seconds"] == 0
    assert body["data_freshness"]["state"] == "fresh"


# ---------------------------------------------------------------------------
# Degraded and unavailable database
# ---------------------------------------------------------------------------


def test_broken_database_degrades_the_field_without_failing_the_probe(monkeypatch):
    """A dependency failure must degrade one field, not the liveness answer."""
    from app.api import health as health_module

    def _explode():
        raise RuntimeError("harness: database deliberately unavailable")

    monkeypatch.setattr(health_module, "_probe_database", _explode)

    response = _client().get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["state"] == "unavailable"
    assert body["database"]["latency_ms"] is None
    # The raised message must not be echoed into a public response.
    assert "deliberately unavailable" not in response.text


def test_slow_database_times_out_instead_of_hanging_the_public_probe(monkeypatch):
    """The probe budget is enforced, so a locked database cannot hang /health."""
    from app.api import health as health_module

    def _slow():
        time.sleep(1.0)
        return health_module.DatabaseHealth(state="ok", latency_ms=1.0)

    monkeypatch.setattr(health_module, "_probe_database", _slow)
    monkeypatch.setattr(health_module, "DB_TIMEOUT_SECONDS", 0.05)

    started = time.perf_counter()
    response = _client().get("/api/v1/health")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert response.json()["database"]["state"] == "unavailable"
    # Must return well before the 1s the abandoned worker is still sleeping for.
    assert elapsed < 0.9, f"probe blocked for {elapsed:.2f}s instead of timing out"

    # Let the abandoned worker finish so it does not starve later probes.
    time.sleep(1.1)


def test_successful_database_check_reports_its_latency():
    body = _client().get("/api/v1/health").json()
    assert body["database"]["state"] == "ok"
    assert body["database"]["latency_ms"] is not None
    assert body["database"]["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# Model availability
# ---------------------------------------------------------------------------


def test_models_report_not_loaded_until_a_forecast_service_exists():
    saved = sys.modules.pop("app.api.forecast", None)
    try:
        response = _client().get("/api/v1/health")
    finally:
        if saved is not None:
            sys.modules["app.api.forecast"] = saved

    body = response.json()
    assert body["models"]["state"] == "not_loaded"
    assert body["models_loaded"] == {"lstm": False, "patchtst": False, "timemixer": False}


def test_model_flags_reflect_the_actual_service_state(monkeypatch):
    """Each model is reported individually from the service, not as one constant."""
    fake_module = types.ModuleType("app.api.forecast")
    fake_module.forecast_service = types.SimpleNamespace(
        lstm_model=object(),
        patchtst_model=None,
        timemixer_model=None,
    )
    monkeypatch.setitem(sys.modules, "app.api.forecast", fake_module)

    body = _client().get("/api/v1/health").json()

    assert body["models"]["state"] == "loaded"
    assert body["models"]["lstm"] is True
    assert body["models"]["patchtst"] is False
    assert body["models"]["timemixer"] is False


# ---------------------------------------------------------------------------
# Public response hygiene
# ---------------------------------------------------------------------------


def test_public_health_response_leaks_no_paths_traces_or_credentials(monkeypatch):
    _use_latest(monkeypatch, observed=None, live=None)
    text = _client().get("/api/v1/health").text

    assert "Traceback" not in text
    assert ".env" not in text
    assert "hydroguard.db" not in text
    # No absolute filesystem paths of any platform.
    assert "Z:\\" not in text
    assert "/Users/" not in text
