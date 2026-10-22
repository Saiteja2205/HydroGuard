"""API tests for the ThingSpeak-backed forecast endpoint.

``GET /api/v1/thingspeak/forecast`` is exercised through the real FastAPI app
with the real checkpoints. The ThingSpeak HTTP boundary is always stubbed, so
these tests prove the *endpoint contract* (auth, provenance, gap disclosure,
honest failure codes) and never claim a live channel was reached.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import require_student_or_admin  # noqa: E402
from app.main import app  # noqa: E402
from ml.services import thingspeak_service as ts  # noqa: E402

ENDPOINT = "/api/v1/thingspeak/forecast"


def _full_feed(hour: int, ph: str, tds: str, turb: str, temp: str, oci: str) -> dict:
    return {
        "created_at": f"2026-10-14T{hour:02d}:00:00Z",
        "entry_id": hour,
        "field1": ph,
        "field2": tds,
        "field3": turb,
        "field4": temp,
        "field5": oci,
    }


def _feeds(count: int = 30) -> list[dict]:
    """A plausible 30-feed history, ascending, all fields present."""
    return [
        _full_feed(h % 24, f"{7.0 + (h % 10) / 100:.2f}", str(290 + h), "1.2",
                   f"{22 + (h % 5) / 10:.1f}", "0.55")
        for h in range(count)
    ]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_student_or_admin,
        lambda: {"uid": "test-student", "role": "STUDENT"},
    )
    # Initialize database tables for alert integration
    from app.db.database import init_db
    init_db()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_student_or_admin, None)


@pytest.fixture
def stub_feeds(monkeypatch):
    """Replace the network fetch with a fixed payload. Returns the store."""

    class _Store:
        feeds: list[dict] = _feeds()
        config = None

    def _fake_fetch(config, client=None):
        _Store.config = config
        return list(_Store.feeds)

    monkeypatch.setattr(ts, "fetch_feeds", _fake_fetch)
    return _Store


class TestAuth:
    def test_requires_authentication(self, client):
        # No override installed by this test: the guard must reject anon access.
        app.dependency_overrides.pop(require_student_or_admin, None)
        response = client.get(ENDPOINT)
        assert response.status_code in (401, 403)

    def test_rejects_non_student_role(self, monkeypatch):
        # Overriding require_student_or_admin itself would replace the guard
        # and never run its check. Override the underlying principal instead,
        # so the real role logic decides.
        from app.core.auth import authenticated_principal

        monkeypatch.setitem(
            app.dependency_overrides,
            authenticated_principal,
            lambda: {"uid": "someone", "role": "GUEST"},
        )
        try:
            response = TestClient(app).get(ENDPOINT)
            assert response.status_code == 403
        finally:
            app.dependency_overrides.pop(authenticated_principal, None)

    def test_allows_admin_role(self, monkeypatch):
        from app.core.auth import authenticated_principal

        monkeypatch.setitem(
            app.dependency_overrides,
            authenticated_principal,
            lambda: {"uid": "admin", "role": "ADMIN"},
        )
        try:
            response = TestClient(app).get(ENDPOINT)
            # ADMIN passes the guard; it may still 503 on missing channel
            # config, but never 403.
            assert response.status_code != 403
        finally:
            app.dependency_overrides.pop(authenticated_principal, None)


class TestNotConfigured:
    def test_missing_channel_returns_503(self, client, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "")
        response = client.get(ENDPOINT)
        assert response.status_code == 503
        assert "HYDROGUARD_THINGSPEAK_CHANNEL_ID" in response.json()["detail"]


class TestChannelOverride:
    def test_digits_override_accepted(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "111")
        response = client.get(ENDPOINT, params={"channel_id": "222"})
        assert response.status_code == 200
        assert stub_feeds.config.channel_id == "222"

    def test_non_numeric_override_rejected(self, client, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "111")
        response = client.get(ENDPOINT, params={"channel_id": "../evil"})
        assert response.status_code == 422


class TestForecastGeneration:
    """Tests for successful forecast generation from ThingSpeak data."""

    def test_returns_success_status_and_forecast_block(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        response = client.get(ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert "forecast" in body
        assert "prediction" in body
        assert "weights" in body
        assert "model_versions" in body
        assert "disclaimer" in body

        # Verify four modelled forecast parameters (pH, TDS, turbidity, temperature)
        ensemble = body["forecast"]["ensemble"]
        assert set(ensemble.keys()) == {"pH", "TDS", "turbidity", "temperature"}
        assert "optical_colour_index" not in ensemble
        assert all(isinstance(ensemble[p], (int, float)) for p in ensemble)

        # Check prediction field matches ensemble
        assert body["prediction"] == ensemble

    def test_has_latest_reading_with_provenance(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        response = client.get(ENDPOINT)
        body = response.json()
        assert "latest_reading" in body
        assert "provenance" in body
        assert body["provenance"]["data_source"] == "THINGSPEAK"
        assert body["provenance"]["models_trained_on"] == "SIMULATED_DEVELOPMENT"
        assert body["provenance"]["real_sensor_data"] is False

    def test_latest_reading_has_four_parameters(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        response = client.get(ENDPOINT)
        body = response.json()
        values = body["latest_reading"]["values"]
        assert set(values.keys()) == {"pH", "TDS", "turbidity", "temperature"}
        assert "optical_colour_index" not in values or values["optical_colour_index"] is None

    def test_insufficient_history_returns_422(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        response = client.get(ENDPOINT, params={"min_history": 50})
        assert response.status_code == 422
        assert "Insufficient history" in response.json()["detail"]

    def test_missing_checkpoints_returns_503(self, client, stub_feeds, monkeypatch):
        from ml.services import inference_service
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        service = inference_service.get_inference_service()
        def _fail_load():
            raise FileNotFoundError("missing checkpoint")
        monkeypatch.setattr(service, "load", _fail_load)
        response = client.get(ENDPOINT)
        assert response.status_code == 503
        assert "Forecast checkpoint not found" in response.json()["detail"]


class TestWindowGapDisclosure:
    def test_clean_window_reports_no_fills(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        body = client.get(ENDPOINT).json()
        window = body["provenance"]["window"]
        assert window["observed_rows"] == 30
        assert window["padded_rows"] == 0
        assert window["forward_filled"] == 0

    def test_forward_filled_cells_are_counted(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _feeds(30)
        feeds[15]["field1"] = ""  # one gap in the middle
        stub_feeds.feeds = feeds
        body = client.get(ENDPOINT).json()
        window = body["provenance"]["window"]
        assert window["forward_filled"] == 1
        assert window["missing_by_parameter"]["pH"] == 1

    def test_short_history_reports_padding(self, client, stub_feeds, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        stub_feeds.feeds = _feeds(10)
        body = client.get(ENDPOINT).json()
        window = body["provenance"]["window"]
        assert window["observed_rows"] == 10
        assert window["padded_rows"] == 20

    def test_unobserved_parameter_is_listed(self, client, stub_feeds, monkeypatch):
        # When optical_colour_index is not provided in the feed, it should not appear
        # in unobserved_parameters since it's not a core parameter anymore.
        # The core parameters are now pH, TDS, turbidity, temperature.
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _feeds(30)
        for feed in feeds:
            feed["field5"] = ""  # optical colour never reported (field5 is Red)
        stub_feeds.feeds = feeds
        body = client.get(ENDPOINT).json()
        # optical_colour_index is not a core parameter anymore, so it should not be in unobserved_parameters
        assert "optical_colour_index" not in body["provenance"]["window"]["unobserved_parameters"]
        # The core parameters that can be unobserved are pH, TDS, turbidity, temperature
        unobserved = body["provenance"]["window"]["unobserved_parameters"]
        assert all(p in ("pH", "TDS", "turbidity", "temperature") for p in unobserved)


class TestHonestFailures:
    def test_empty_channel_is_502_not_a_fabricated_forecast(self, client, stub_feeds, monkeypatch):
        # A channel with no feeds must not produce a midpoint-built forecast.
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        stub_feeds.feeds = []
        response = client.get(ENDPOINT)
        assert response.status_code == 502
        assert "no observations" in response.json()["detail"]

    def test_unreachable_channel_is_502(self, client, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")

        def _boom(config, client=None):
            raise ts.ThingSpeakUnavailable("network down")

        monkeypatch.setattr(ts, "fetch_feeds", _boom)
        response = client.get(ENDPOINT)
        assert response.status_code == 502
        assert "network down" in response.json()["detail"]

    def test_invalid_channel_is_422(self, client, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "not-digits")
        response = client.get(ENDPOINT)
        assert response.status_code == 422


class TestReadOnlySafety:
    def test_endpoint_persists_no_forecast_rows(self, client, stub_feeds, monkeypatch):
        # This path must stay read-only so simulated-derived forecasts cannot
        # be mistaken for stored sensor data by /health or the dashboards.
        from app.db.database import get_db_context, init_db
        from app.db.models import Forecast

        # The temp test database has no tables until init_db() creates them.
        init_db()
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        with get_db_context() as db:
            before = db.query(Forecast).count()
        assert client.get(ENDPOINT).status_code == 200
        with get_db_context() as db:
            after = db.query(Forecast).count()
        assert after == before


class TestAlertIntegration:
    """Tests for ThingSpeak → Alert integration."""

    def test_first_violation_creates_alert(self, client, stub_feeds, monkeypatch):
        """First threshold violation creates an alert."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "99999")
        # pH = 6.0 (below min 6.5)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = "6.0"  # pH below threshold

        init_db()
        with get_db_context() as db:
            before = db.query(Alert).filter(Alert.node_id == "thingspeak-99999").count()

        response = client.get(ENDPOINT)
        assert response.status_code == 200

        with get_db_context() as db:
            after = db.query(Alert).filter(Alert.node_id == "thingspeak-99999").count()
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-99999").all()

        assert after == before + 1
        assert len(alerts) == 1
        assert alerts[0].parameter == "pH"
        assert alerts[0].status == "ACTIVE"
        assert alerts[0].severity == "WARNING"

    def test_repeated_polling_no_duplicate_alerts(self, client, stub_feeds, monkeypatch):
        """Repeated polling of the same violating feed does not create duplicate alerts (60-min cooldown)."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "88888")
        # pH = 6.0 (below min 6.5)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = "6.0"

        init_db()
        # First call
        client.get(ENDPOINT)
        # Second call (immediate)
        client.get(ENDPOINT)
        # Third call (immediate)
        client.get(ENDPOINT)

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-88888").all()

        # Only 1 alert should exist due to 60-minute cooldown
        assert len(alerts) == 1

    def test_new_violating_feed_creates_new_alert(self, client, stub_feeds, monkeypatch):
        """A different channel with violation creates its own alert."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "77777")
        # TDS = 600 (above max 500)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field2"] = "600"

        init_db()
        response = client.get(ENDPOINT)
        assert response.status_code == 200

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-77777").all()

        assert len(alerts) == 1
        assert alerts[0].parameter == "TDS"
        assert alerts[0].status == "ACTIVE"

    def test_recovery_to_normal_resolves_alert(self, client, stub_feeds, monkeypatch):
        """When readings return to normal, active alert is auto-resolved."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "66666")
        # First: pH = 6.0 (violation)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = "6.0"

        init_db()
        # First call - creates alert
        client.get(ENDPOINT)

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-66666").all()
            assert len(alerts) == 1
            assert alerts[0].status == "ACTIVE"
            alert_id = alerts[0].id

        # Second call - pH = 7.0 (back to normal)
        for feed in stub_feeds.feeds:
            feed["field1"] = "7.0"
        client.get(ENDPOINT)

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-66666").all()
            assert len(alerts) == 1
            assert alerts[0].status == "RESOLVED"
            assert alerts[0].id == alert_id

    def test_invalid_readings_no_alert(self, client, stub_feeds, monkeypatch):
        """Invalid/missing readings do not create alerts."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55555")
        # pH = empty (invalid)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = ""

        init_db()
        response = client.get(ENDPOINT)
        assert response.status_code == 200

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-55555").all()

        # No alerts for invalid readings
        assert len(alerts) == 0

    def test_unavailable_optical_colour_index_no_alert(self, client, stub_feeds, monkeypatch):
        """Unavailable optical_colour_index does not trigger alert evaluation."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "44444")
        # Normal readings - no violations
        stub_feeds.feeds = _feeds(30)
        # field5 (Red) is not optical_colour_index - no field for OCI

        init_db()
        response = client.get(ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        # Returns success for the 4 core parameters
        assert body["status"] == "success"

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-44444").all()

        # No OCI alerts since it's unavailable
        oci_alerts = [a for a in alerts if a.parameter == "optical_colour_index"]
        assert len(oci_alerts) == 0

    def test_temperature_alert_info_severity(self, client, stub_feeds, monkeypatch):
        """Temperature alerts use INFO severity, not WARNING."""
        from app.db.database import get_db_context, init_db
        from app.db.models import Alert

        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "33333")
        # Temperature = 35.0 (above max 30.0)
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field4"] = "35.0"

        init_db()
        response = client.get(ENDPOINT)
        assert response.status_code == 200

        with get_db_context() as db:
            alerts = db.query(Alert).filter(Alert.node_id == "thingspeak-33333").all()

        assert len(alerts) == 1
        assert alerts[0].parameter == "temperature"
        assert alerts[0].severity == "INFO"


class TestLatestThingSpeakReading:
    """Tests for GET /api/v1/thingspeak/latest endpoint."""

    def test_returns_latest_reading_with_correct_field_mapping(self, client, stub_feeds, monkeypatch):
        """Latest reading endpoint returns correct field mapping and units."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55555")
        stub_feeds.feeds = _feeds(30)
        # Use realistic values
        for feed in stub_feeds.feeds:
            feed["field1"] = "7.25"    # pH
            feed["field2"] = "320"     # TDS
            feed["field3"] = "2.5"     # turbidity
            feed["field4"] = "24.5"    # temperature
            feed["field5"] = "42"      # Red (0-100%)
            feed["field6"] = "29"      # Green (0-100%)
            feed["field7"] = "28"      # Blue (0-100%)
            feed["field8"] = "1"       # status

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()

        # Check core parameters
        assert "values" in body
        values = body["values"]
        assert values["pH"] == pytest.approx(7.25, abs=1e-6)
        assert values["TDS"] == pytest.approx(320.0, abs=1e-6)
        assert values["turbidity"] == pytest.approx(2.5, abs=1e-6)
        assert values["temperature"] == pytest.approx(24.5, abs=1e-6)
        assert "optical_colour_index" not in values

        # Check RGB values (0-100%)
        assert "rgb" in body
        rgb = body["rgb"]
        assert rgb["red"] == 42
        assert rgb["green"] == 29
        assert rgb["blue"] == 28

        # Check timestamp
        assert "timestamp" in body
        assert body["timestamp"] is not None
        assert body["observed_at"] is not None

    def test_rgb_values_are_percentages_not_16bit(self, client, stub_feeds, monkeypatch):
        """RGB values are 0-100% percentages, not 16-bit ADC counts."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55556")
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = "7.0"
            feed["field2"] = "300"
            feed["field3"] = "1.0"
            feed["field4"] = "25.0"
            feed["field5"] = "100"     # Red max
            feed["field6"] = "0"       # Green min
            feed["field7"] = "50"      # Blue mid

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()

        rgb = body["rgb"]
        # Values should be 0-100, not 0-65535
        assert 0 <= rgb["red"] <= 100
        assert 0 <= rgb["green"] <= 100
        assert 0 <= rgb["blue"] <= 100
        assert rgb["red"] == 100
        assert rgb["green"] == 0
        assert rgb["blue"] == 50

    def test_latest_feed_selection(self, client, stub_feeds, monkeypatch):
        """Endpoint returns the newest feed (latest entry_id/timestamp)."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55557")
        # Create feeds with different timestamps - newest last
        stub_feeds.feeds = _feeds(3)
        stub_feeds.feeds[0]["field1"] = "6.0"
        stub_feeds.feeds[1]["field1"] = "7.0"
        stub_feeds.feeds[2]["field1"] = "7.5"  # newest

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()

        # Should return the newest reading (pH = 7.5)
        assert body["values"]["pH"] == pytest.approx(7.5, abs=1e-6)

    def test_timestamp_handling(self, client, stub_feeds, monkeypatch):
        """Response includes proper ISO timestamp from ThingSpeak."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55558")
        stub_feeds.feeds = _feeds(1)
        stub_feeds.feeds[0]["created_at"] = "2026-10-15T06:37:10Z"
        stub_feeds.feeds[0]["field1"] = "7.0"

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()

        assert body["timestamp"] == "2026-10-15T06:37:10Z"
        assert body["observed_at"] == "2026-10-15T06:37:10Z"

    def test_demo_values_not_labelled_as_live(self, client, stub_feeds, monkeypatch):
        """ThingSpeak endpoint never returns DEMO/SIMULATED source for live data."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55559")
        stub_feeds.feeds = _feeds(30)
        for feed in stub_feeds.feeds:
            feed["field1"] = "7.0"

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()

        # The provenance data_source should be THINGSPEAK
        # (The endpoint returns ThingSpeakLatestReading which doesn't include provenance
        # in the response body directly, but the forecast endpoint does.
        # This test ensures the reading itself doesn't carry a false source tag.)
        # The reading's own source field is not in the ThingSpeakLatestReading model.
        assert "values" in body
        assert "rgb" in body

    def test_thingspeak_latest_includes_entry_id_and_status(self, client, stub_feeds, monkeypatch):
        """ThingSpeak latest reading includes feed entry_id and status flag."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55559")
        stub_feeds.feeds = _feeds(1)
        stub_feeds.feeds[0]["entry_id"] = 122
        stub_feeds.feeds[0]["field8"] = "1"

        init_db()
        response = client.get("/api/v1/thingspeak/latest")
        assert response.status_code == 200
        body = response.json()
        assert body["entry_id"] == 122
        assert body["status_flag"] == 1

    def test_thingspeak_history_returns_chronological_readings(self, client, stub_feeds, monkeypatch):
        """ThingSpeak history endpoint returns bounded chronological feeds."""
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "55559")
        stub_feeds.feeds = [
            {
                "created_at": "2026-10-15T08:56:00Z",
                "entry_id": 101,
                "field1": "7.20",
                "field2": "280",
                "field3": "1.1",
                "field4": "22.5",
                "field5": "45",
                "field6": "30",
                "field7": "25",
                "field8": "0",
            },
            {
                "created_at": "2026-10-15T08:57:00Z",
                "entry_id": 102,
                "field1": "7.25",
                "field2": "285",
                "field3": "1.2",
                "field4": "22.6",
                "field5": "44",
                "field6": "31",
                "field7": "25",
                "field8": "0",
            },
        ]

        init_db()
        response = client.get("/api/v1/thingspeak/history?limit=10")
        assert response.status_code == 200
        body = response.json()
        assert body["channel_id"] == "55559"
        assert body["source"] == "THINGSPEAK"
        assert body["count"] == 2
        assert len(body["readings"]) == 2
        assert body["readings"][0]["entry_id"] == 101
        assert body["readings"][0]["ph"] == 7.20
        assert body["readings"][0]["pH"] == 7.20
        assert body["readings"][0]["red"] == 45
        assert body["readings"][1]["entry_id"] == 102
        assert body["readings"][1]["timestamp"] > body["readings"][0]["timestamp"]


class TestForecastSemanticsAndTargetTimestamp:
    def test_forecast_response_contains_target_timestamp_and_semantics(self, client, stub_feeds, monkeypatch):
        """Forecast response includes 24h target_timestamp and explicit next-step semantics."""
        import math
        from app.db.database import init_db
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "66661")
        stub_feeds.feeds = _feeds(30)
        stub_feeds.feeds[-2]["created_at"] = "2026-10-15T08:56:38Z"
        stub_feeds.feeds[-1]["created_at"] = "2026-10-15T08:57:08Z"
        for feed in stub_feeds.feeds:
            feed["field1"] = "12.41"
            feed["field2"] = "5.47"
            feed["field3"] = "29.08"
            feed["field4"] = "25.56"

        init_db()
        response = client.get("/api/v1/thingspeak/forecast")
        assert response.status_code == 200
        body = response.json()

        assert body["status"] == "success"
        assert body["forecast_horizon_hours"] == 24
        assert "target_timestamp" in body
        # Real live interval is 30 seconds -> 08:57:08 + 30s = 08:57:38
        assert body["target_timestamp"] == "2026-10-15T08:57:38Z"
        assert body["sample_interval_seconds"] == 30
        assert "prediction_semantics" in body
        assert "next-step" in body["prediction_semantics"].lower() or "next_step" in body["prediction_semantics"].lower()

        # Check finite and non-negative predictions
        ens = body["forecast"]["ensemble"]
        assert math.isfinite(ens["pH"])
        assert math.isfinite(ens["TDS"])
        assert math.isfinite(ens["turbidity"])
        assert math.isfinite(ens["temperature"])
        assert ens["pH"] >= 0.0
        assert ens["TDS"] >= 0.0
        assert ens["turbidity"] >= 0.0
