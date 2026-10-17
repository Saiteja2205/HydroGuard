"""Tests for the ThingSpeak ingestion service.

These cover the parsing and gap-filling contract against *stubbed* feed
payloads shaped exactly like the live API (verified ascending order, ISO-8601
timestamps). No test touches the network: the HTTP boundary is injected or
bypassed entirely, so a green run here says nothing about a live channel and
must not be reported as if it did.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.services.thingspeak_service import (  # noqa: E402
    DEFAULT_RESULTS,
    ThingSpeakConfig,
    ThingSpeakInvalidChannel,
    ThingSpeakNotConfigured,
    ThingSpeakUnavailable,
    build_feed_url,
    load_config_from_env,
    parse_feeds,
)


def _full_feed(hour: int, ph: str, tds: str, turb: str, temp: str, oci: str) -> dict:
    """Build one feed in the live API's ascending, ISO-8601 shape."""
    return {
        "created_at": f"2026-10-14T{hour:02d}:00:00Z",
        "entry_id": hour,
        "field1": ph,
        "field2": tds,
        "field3": turb,
        "field4": temp,
        "field5": oci,
    }


class TestConfigLoading:
    def test_missing_channel_is_not_configured(self):
        config = load_config_from_env({})
        assert config.configured is False
        assert config.channel_id == ""

    def test_channel_and_key_read_from_env(self):
        config = load_config_from_env(
            {"HYDROGUARD_THINGSPEAK_CHANNEL_ID": "123456", "HYDROGUARD_THINGSPEAK_READ_API_KEY": "k"}
        )
        assert config.configured is True
        assert config.channel_id == "123456"
        assert config.read_api_key == "k"

    def test_default_results_is_at_least_the_model_window(self):
        # The models need 30 rows; a smaller configured value must not shrink
        # the request below that, or the window could never be satisfied.
        config = load_config_from_env({"HYDROGUARD_THINGSPEAK_CHANNEL_ID": "1", "HYDROGUARD_THINGSPEAK_RESULTS": "5"})
        assert config.results == DEFAULT_RESULTS

    def test_malformed_results_falls_back_to_default(self):
        config = load_config_from_env({"HYDROGUARD_THINGSPEAK_CHANNEL_ID": "1", "HYDROGUARD_THINGSPEAK_RESULTS": "abc"})
        assert config.results == DEFAULT_RESULTS


class TestUrlBuilding:
    def test_public_channel_has_no_key(self):
        url = build_feed_url(ThingSpeakConfig(channel_id="999", results=30))
        assert url == "https://api.thingspeak.com/channels/999/feeds.json?results=30"
        assert "api_key" not in url

    def test_private_channel_appends_key(self):
        url = build_feed_url(ThingSpeakConfig(channel_id="999", read_api_key="SECRET", results=30))
        assert "api_key=SECRET" in url

    def test_unconfigured_raises(self):
        with pytest.raises(ThingSpeakNotConfigured):
            build_feed_url(ThingSpeakConfig(channel_id=""))

    @pytest.mark.parametrize("bad", ["../evil", "12 34", "abc", "1;drop", "1&x=2"])
    def test_non_numeric_channel_rejected(self, bad):
        # The channel id is interpolated into a URL path, so anything that is
        # not digits could redirect the request or smuggle query parameters.
        with pytest.raises(ThingSpeakInvalidChannel):
            build_feed_url(ThingSpeakConfig(channel_id=bad))


class TestParsing:
    def test_window_is_ascending_oldest_first(self):
        cfg = ThingSpeakConfig(channel_id="1", results=5)
        feeds = [_full_feed(h, str(7.0 + h / 10), "300", "1", "22", "0.5") for h in (0, 1, 2)]
        window = parse_feeds(feeds, cfg)
        # Newest feed (02:00) must be the LAST row, not the first.
        assert window.values[-1][0] == pytest.approx(7.2)
        assert window.values[0][0] == pytest.approx(7.0)

    def test_short_history_is_padded_at_the_head(self):
        cfg = ThingSpeakConfig(channel_id="1", results=5)
        feeds = [_full_feed(h, "7.0", "300", "1", "22", "0.5") for h in (0, 1, 2)]
        window = parse_feeds(feeds, cfg)
        assert window.window_size == 5
        assert window.observed_rows == 3
        assert window.padded_rows == 2
        # Padded head rows repeat the first observed values.
        assert window.values[0] == window.values[2]

    def test_causal_forward_fill_never_uses_the_future(self):
        cfg = ThingSpeakConfig(channel_id="1", results=3)
        feeds = [
            _full_feed(0, "7.0", "300", "1.0", "22", "0.5"),
            _full_feed(1, "", "310", "1.0", "22", "0.5"),  # pH absent
            _full_feed(2, "7.2", "310", "1.1", "23", "0.55"),
        ]
        window = parse_feeds(feeds, cfg)
        # 01:00 pH carries 7.0 from 00:00 (past), never 7.2 from 02:00.
        assert window.values[1][0] == pytest.approx(7.0)
        assert window.forward_filled == 1
        assert window.leading_filled == 0

    def test_leading_gap_repeats_first_available(self):
        cfg = ThingSpeakConfig(channel_id="1", results=3)
        feeds = [
            _full_feed(0, "7.0", "300", "", "22", "0.5"),  # turbidity absent at head
            _full_feed(1, "7.0", "310", "1.0", "22", "0.5"),
            _full_feed(2, "7.2", "310", "1.1", "23", "0.55"),
        ]
        window = parse_feeds(feeds, cfg)
        assert window.values[0][2] == pytest.approx(1.0)
        assert window.leading_filled == 1
        assert window.forward_filled == 0

    def test_out_of_range_value_becomes_missing_not_passthrough(self):
        cfg = ThingSpeakConfig(channel_id="1", results=1)
        feeds = [_full_feed(0, "99.0", "300", "1", "22", "0.5")]  # pH 99 impossible
        window = parse_feeds(feeds, cfg)
        assert window.values[0][0] != pytest.approx(99.0)
        assert "pH" in window.unobserved_parameters

    def test_unparseable_timestamp_is_none_not_now(self):
        cfg = ThingSpeakConfig(channel_id="1", results=1)
        feeds = [
            {
                "created_at": "not-a-timestamp",
                "field1": "7.0",
                "field2": "300",
                "field3": "1",
                "field4": "22",
                "field5": "0.5",
            }
        ]
        window = parse_feeds(feeds, cfg)
        # A malformed timestamp must not be silently replaced with "now".
        assert window.latest_timestamp is None
        assert window.timestamps == (None,)

    def test_naive_timestamp_is_interpreted_as_utc(self):
        cfg = ThingSpeakConfig(channel_id="1", results=1)
        feeds = [
            {
                "created_at": "2026-10-14 03:00:00 UTC",
                "field1": "7.0",
                "field2": "300",
                "field3": "1",
                "field4": "22",
                "field5": "0.5",
            }
        ]
        window = parse_feeds(feeds, cfg)
        assert window.latest_timestamp == datetime(2026, 10, 14, 3, 0, tzinfo=timezone.utc)

    def test_empty_feed_list_yields_full_window_honestly_flagged(self):
        cfg = ThingSpeakConfig(channel_id="1", results=5)
        window = parse_feeds([], cfg)
        assert window.window_size == 5
        assert window.observed_rows == 0
        assert window.latest_timestamp is None
        assert len(window.unobserved_parameters) == 4

    def test_more_feeds_than_window_trims_to_newest(self):
        cfg = ThingSpeakConfig(channel_id="1", results=3)
        feeds = [_full_feed(h, str(7.0 + h / 100), "300", "1", "22", "0.5") for h in range(10)]
        window = parse_feeds(feeds, cfg)
        assert window.window_size == 3
        assert window.values[-1][0] == pytest.approx(7.09)
        assert window.padded_rows == 0

    def test_missing_by_parameter_counts_before_filling(self):
        cfg = ThingSpeakConfig(channel_id="1", results=3)
        feeds = [
            _full_feed(0, "7.0", "300", "1", "22", "0.5"),
            _full_feed(1, "", "310", "1", "22", "0.5"),
            _full_feed(2, "7.2", "310", "1", "22", "0.5"),
        ]
        window = parse_feeds(feeds, cfg)
        assert window.missing_by_parameter["pH"] == 1
        assert window.missing_by_parameter["TDS"] == 0


class TestFetchErrors:
    def test_unavailable_is_raised_for_transport_failure(self, monkeypatch):
        import httpx
        from ml.services import thingspeak_service as ts

        class BoomClient:
            def get(self, url):
                raise httpx.ConnectError("no route")

            def close(self):
                pass

        cfg = ThingSpeakConfig(channel_id="1")
        with pytest.raises(ThingSpeakUnavailable):
            ts.fetch_feeds(cfg, client=BoomClient())

    def test_non_200_is_unavailable(self):
        import httpx
        from ml.services import thingspeak_service as ts

        class FakeResponse:
            status_code = 500

            def json(self):
                return {}

        class FakeClient:
            def get(self, url):
                return FakeResponse()

            def close(self):
                pass

        with pytest.raises(ThingSpeakUnavailable):
            ts.fetch_feeds(ThingSpeakConfig(channel_id="1"), client=FakeClient())

    def test_non_json_payload_is_unavailable(self):
        from ml.services import thingspeak_service as ts

        class FakeResponse:
            status_code = 200

            def json(self):
                raise ValueError("no json")

        class FakeClient:
            def get(self, url):
                return FakeResponse()

            def close(self):
                pass

        with pytest.raises(ThingSpeakUnavailable):
            ts.fetch_feeds(ThingSpeakConfig(channel_id="1"), client=FakeClient())

    def test_missing_feeds_key_is_unavailable(self):
        from ml.services import thingspeak_service as ts

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"channel": {}}

        class FakeClient:
            def get(self, url):
                return FakeResponse()

            def close(self):
                pass

        with pytest.raises(ThingSpeakUnavailable):
            ts.fetch_feeds(ThingSpeakConfig(channel_id="1"), client=FakeClient())

    def test_valid_payload_returns_feeds(self):
        from ml.services import thingspeak_service as ts

        payload = {"feeds": [{"created_at": "2026-10-14T00:00:00Z", "field1": "7.0"}]}

        class FakeResponse:
            status_code = 200

            def json(self):
                return payload

        class FakeClient:
            def get(self, url):
                return FakeResponse()

            def close(self):
                pass

        feeds = ts.fetch_feeds(ThingSpeakConfig(channel_id="1"), client=FakeClient())
        assert len(feeds) == 1
        assert feeds[0]["field1"] == "7.0"
