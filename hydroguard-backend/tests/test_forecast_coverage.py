"""Tests for Phase 4: Forecast data coverage, sufficiency enforcement, and provenance.

Verifies:
1. Healthy window with valid data produces forecast successfully.
2. Window with 0 usable pH observations fails with HTTP 422.
3. Window with 0 usable TDS observations fails with HTTP 422.
4. Window with 0 usable turbidity observations fails with HTTP 422.
5. Window with 0 usable temperature observations fails with HTTP 422.
6. Sensor dropouts (pH=0.0, TDS=0.0, Temp=0.0) are not counted as observed.
7. Unobserved parameters are rejected (422) instead of midpoint synthesized.
8. Short gaps with valid earlier observations are causally forward-filled.
9. Provenance accurately reports source_rows_fetched, observed_rows, and observed_by_parameter.
10. Chronological order is preserved (no future leakage).
11. Source rows fetched vs observed rows accurately separated when feeds contain invalid data.
12. Backward compatibility of forecast provenance schema.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth import require_student_or_admin  # noqa: E402
from app.db.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from ml.services import thingspeak_service as ts  # noqa: E402
from ml.services.thingspeak_service import ThingSpeakConfig, parse_feeds  # noqa: E402

ENDPOINT = "/api/v1/thingspeak/forecast"


def _make_feed(
    entry_id: int,
    ph: str = "7.20",
    tds: str = "300.0",
    turbidity: str = "1.5",
    temperature: str = "24.0",
    oci: str = "0.55",
    timestamp: str | None = None,
) -> dict:
    ts_str = timestamp or f"2026-10-14T{entry_id % 24:02d}:00:00Z"
    return {
        "created_at": ts_str,
        "entry_id": entry_id,
        "field1": ph,
        "field2": tds,
        "field3": turbidity,
        "field4": temperature,
        "field5": oci,
    }


def _make_healthy_feeds(count: int = 30) -> list[dict]:
    return [_make_feed(i + 1) for i in range(count)]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_student_or_admin,
        lambda: {"uid": "coverage-test-user", "role": "STUDENT"},
    )
    init_db()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_student_or_admin, None)


@pytest.fixture
def stub_feeds(monkeypatch):
    class _Store:
        feeds: list[dict] = _make_healthy_feeds(30)
        config: ThingSpeakConfig | None = None

    def _fake_fetch(config, client=None):
        _Store.config = config
        return list(_Store.feeds)

    monkeypatch.setattr(ts, "fetch_feeds", _fake_fetch)
    return _Store


class TestForecastDataQualityAndCoverage:
    """Covers Phase 4 sufficiency checks and provenance."""

    def test_scenario_1_healthy_window_forecast_success(self, client, stub_feeds, monkeypatch):
        """1. Healthy window with valid data across all 4 parameters produces forecast successfully."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        stub_feeds.feeds = _make_healthy_feeds(30)

        response = client.get(ENDPOINT)
        assert response.status_code == 200
        body = response.json()

        assert body["provenance"]["data_source"] == "THINGSPEAK"
        assert body["provenance"]["channel_id"] == "12345"
        assert "provenance" in body
        window = body["provenance"]["window"]
        assert window["source_rows_fetched"] == 30
        assert window["observed_rows"] == 30
        assert window["observed_by_parameter"]["pH"] == 30
        assert window["observed_by_parameter"]["TDS"] == 30
        assert window["observed_by_parameter"]["turbidity"] == 30
        assert window["observed_by_parameter"]["temperature"] == 30

    def test_scenario_2_zero_ph_observations_fails_422(self, client, stub_feeds, monkeypatch):
        """2. Window with 0 usable pH observations fails with HTTP 422 explaining insufficient pH observations."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(30)
        # All pH values set to empty / missing
        for f in feeds:
            f["field1"] = ""
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        body = response.json()
        assert "Insufficient valid observations for parameter(s)" in body["detail"]
        assert "'pH'" in body["detail"]

    def test_scenario_3_zero_tds_observations_fails_422(self, client, stub_feeds, monkeypatch):
        """3. Window with 0 usable TDS observations fails with HTTP 422 explaining insufficient TDS observations."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(30)
        for f in feeds:
            f["field2"] = ""
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        body = response.json()
        assert "Insufficient valid observations for parameter(s)" in body["detail"]
        assert "'TDS'" in body["detail"]

    def test_scenario_4_zero_turbidity_observations_fails_422(self, client, stub_feeds, monkeypatch):
        """4. Window with 0 usable turbidity observations fails with HTTP 422 explaining insufficient turbidity observations."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(30)
        for f in feeds:
            f["field3"] = ""
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        body = response.json()
        assert "Insufficient valid observations for parameter(s)" in body["detail"]
        assert "'turbidity'" in body["detail"]

    def test_scenario_5_zero_temperature_observations_fails_422(self, client, stub_feeds, monkeypatch):
        """5. Window with 0 usable temperature observations fails with HTTP 422 explaining insufficient temperature observations."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(30)
        for f in feeds:
            f["field4"] = ""
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        body = response.json()
        assert "Insufficient valid observations for parameter(s)" in body["detail"]
        assert "'temperature'" in body["detail"]

    def test_scenario_6_sensor_dropouts_not_counted_as_observed(self, client, stub_feeds, monkeypatch):
        """6. Sensor dropouts (pH=0.0, TDS=0.0, Temp=0.0) are NOT counted as observed."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(30)
        # All feeds have 0.0 dropouts on pH
        for f in feeds:
            f["field1"] = "0.0"
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        body = response.json()
        assert "Insufficient valid observations for parameter(s)" in body["detail"]
        assert "'pH'" in body["detail"]

        # Directly verify parse_feeds window provenance
        config = ThingSpeakConfig(channel_id="12345")
        window = parse_feeds(feeds, config)
        assert window.observed_by_parameter["pH"] == 0
        assert window.observed_by_parameter["TDS"] == 30
        assert window.source_rows_fetched == 30

    def test_scenario_7_unobserved_parameter_never_synthesized_for_models(self, client, stub_feeds, monkeypatch):
        """7. Window where a parameter is completely unobserved fails 422, never synthesized for ML."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = [
            _make_feed(i, ph="7.2", tds="350", turbidity="1.1", temperature="invalid_string")
            for i in range(1, 15)
        ]
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 422
        assert "'temperature'" in response.json()["detail"]

    def test_scenario_8_short_gap_causally_filled_with_valid_earlier_obs(self, client, stub_feeds, monkeypatch):
        """8. Short gap with a valid earlier observation is causally forward-filled and succeeds."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = _make_healthy_feeds(10)
        # Feed 1 has valid pH (7.4), feeds 2-10 have missing pH
        for f in feeds[1:]:
            f["field1"] = ""
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 200
        body = response.json()
        prov = body["provenance"]["window"]
        # pH had 1 valid observation, so observed_by_parameter['pH'] == 1
        assert prov["observed_by_parameter"]["pH"] == 1
        # Gaps were filled causally
        assert prov["forward_filled"] > 0
        assert prov["source_rows_fetched"] == 10

    def test_scenario_9_provenance_accurately_reports_all_metrics(self, client, stub_feeds, monkeypatch):
        """9. Provenance accurately reports source_rows_fetched, observed_rows, and observed_by_parameter."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        feeds = [
            _make_feed(1, ph="7.1", tds="250", turbidity="1.0", temperature="23.0"),
            _make_feed(2, ph="7.2", tds="260", turbidity="1.1", temperature="23.5"),
            _make_feed(3, ph="7.3", tds="270", turbidity="1.2", temperature="24.0"),
        ]
        stub_feeds.feeds = feeds

        response = client.get(ENDPOINT)
        assert response.status_code == 200
        prov = response.json()["provenance"]["window"]
        assert prov["source_rows_fetched"] == 3
        assert prov["observed_rows"] == 3
        assert prov["observed_by_parameter"] == {
            "pH": 3,
            "TDS": 3,
            "turbidity": 3,
            "temperature": 3,
        }
        assert prov["padded_rows"] == 27
        assert prov["window_size"] == 30

    def test_scenario_10_chronological_order_no_future_leakage(self):
        """10. Chronological order is preserved oldest-to-newest, no future leakage."""
        feeds = [
            _make_feed(1, ph="7.10", timestamp="2026-10-14T10:00:00Z"),
            _make_feed(2, ph="7.20", timestamp="2026-10-14T10:01:00Z"),
            _make_feed(3, ph="7.30", timestamp="2026-10-14T10:02:00Z"),
        ]
        config = ThingSpeakConfig(channel_id="12345")
        window = parse_feeds(feeds, config)

        # In the 30-row window, the last 3 rows are feeds 1, 2, 3
        assert window.values[-3][0] == pytest.approx(7.10, abs=0.01)
        assert window.values[-2][0] == pytest.approx(7.20, abs=0.01)
        assert window.values[-1][0] == pytest.approx(7.30, abs=0.01)
        # Verify timestamp progression
        assert window.timestamps[-3] < window.timestamps[-2] < window.timestamps[-1]

    def test_scenario_11_source_rows_fetched_vs_observed_rows_separation(self):
        """11. Accurate count of source_rows_fetched vs observed_rows when some feeds contain only invalid data."""
        feeds = [
            # Row 1: all valid
            _make_feed(1, ph="7.10", tds="300", turbidity="1.2", temperature="22.0"),
            # Row 2: all dropouts / unparseable
            _make_feed(2, ph="0.0", tds="0.0", turbidity="-5.0", temperature="0.0"),
            # Row 3: only pH is valid, rest missing
            _make_feed(3, ph="7.30", tds="", turbidity="", temperature=""),
        ]
        config = ThingSpeakConfig(channel_id="12345")
        window = parse_feeds(feeds, config)

        assert window.source_rows_fetched == 3
        # Row 1 and Row 3 contain at least one valid observation; Row 2 has none
        assert window.observed_rows == 2
        assert window.observed_by_parameter["pH"] == 2
        assert window.observed_by_parameter["TDS"] == 1
        assert window.observed_by_parameter["turbidity"] == 1
        assert window.observed_by_parameter["temperature"] == 1

    def test_scenario_12_backward_compatibility_provenance_schema(self, client, stub_feeds, monkeypatch):
        """12. Existing valid forecast paths and provenance schema remain fully backward compatible."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "12345")
        stub_feeds.feeds = _make_healthy_feeds(30)

        response = client.get(ENDPOINT)
        assert response.status_code == 200
        data = response.json()

        # Legacy fields exist and are valid
        prov = data["provenance"]["window"]
        for legacy_key in ("window_size", "observed_rows", "forward_filled", "leading_filled", "padded_rows", "missing_by_parameter", "unobserved_parameters", "rgb_missing_by_channel"):
            assert legacy_key in prov

        # New fields exist
        assert "source_rows_fetched" in prov
        assert "observed_by_parameter" in prov
        assert isinstance(prov["source_rows_fetched"], int)
        assert isinstance(prov["observed_by_parameter"], dict)
