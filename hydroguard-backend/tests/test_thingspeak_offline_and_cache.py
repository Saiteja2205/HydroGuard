"""Tests for ThingSpeak endpoints when hardware is offline and during network outages.

Verifies:
1. Retrieving old/stale readings when sensor hardware is offline.
2. Fallback to in-memory and database cache when upstream ThingSpeak is unreachable.
3. History endpoint retrieval and offline cache fallback.
4. Actionable 503 diagnostic when no channel is configured.
5. Handling of empty feeds without unhandled exceptions.
6. Explicit channel_id query parameter routing.
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
from app.db.database import get_db, init_db  # noqa: E402
from app.db.models import SensorReading  # noqa: E402
from app.db.repositories import NodeRepository  # noqa: E402
from app.main import app  # noqa: E402
from app.api import forecast as forecast_api  # noqa: E402
from ml.services import thingspeak_service as ts  # noqa: E402


@pytest.fixture
def auth_client(monkeypatch):
    """Test client with student authentication override and initialized DB."""
    monkeypatch.setitem(
        app.dependency_overrides,
        require_student_or_admin,
        lambda: {"uid": "test-student-offline", "role": "STUDENT"},
    )
    init_db()
    # Clear in-memory cache between tests
    forecast_api._thingspeak_feed_cache.clear()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_student_or_admin, None)
        forecast_api._thingspeak_feed_cache.clear()


class TestThingSpeakHardwareOffline:
    """Verifies behavior when sensor hardware is offline but ThingSpeak has feeds."""

    def test_stale_reading_returned_with_offline_hardware_status(self, auth_client, monkeypatch):
        """When hardware hasn't sent data recently, endpoint returns data marked stale and offline."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")

        stale_feeds = [
            {
                "created_at": "2026-10-15T08:57:08Z",
                "entry_id": 122,
                "field1": "12.41",
                "field2": "5.47",
                "field3": "29.08",
                "field4": "25.56",
                "field5": "40",
                "field6": "29",
                "field7": "30",
                "field8": "0",
            }
        ]

        monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: list(stale_feeds))

        resp = auth_client.get("/api/v1/thingspeak/latest")
        assert resp.status_code == 200
        data = resp.json()

        assert data["channel_id"] == "244357"
        assert data["entry_id"] == 122
        assert data["is_stale"] is True
        assert data["is_cached"] is False
        assert data["upstream_status"] == "reachable"
        assert "offline" in data["hardware_status"].lower()
        assert data["values"]["pH"] == pytest.approx(12.41, abs=1e-3)
        assert data["values"]["TDS"] == pytest.approx(5.47, abs=1e-3)
        assert data["values"]["turbidity"] == pytest.approx(29.08, abs=1e-3)
        assert data["values"]["temperature"] == pytest.approx(25.56, abs=1e-3)
        assert data["rgb"]["red"] == 40
        assert data["rgb"]["green"] == 29
        assert data["rgb"]["blue"] == 30

    def test_upstream_failure_falls_back_to_in_memory_cache(self, auth_client, monkeypatch):
        """When upstream fails after a successful fetch, returns cached reading with is_cached=True."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")

        sample_feeds = [
            {
                "created_at": "2026-10-15T08:57:08Z",
                "entry_id": 122,
                "field1": "7.40",
                "field2": "150.0",
                "field3": "1.5",
                "field4": "24.0",
                "field5": "50",
                "field6": "45",
                "field7": "40",
                "field8": "0",
            }
        ]

        # 1. First call: upstream works
        monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: list(sample_feeds))
        resp1 = auth_client.get("/api/v1/thingspeak/latest")
        assert resp1.status_code == 200
        assert resp1.json()["is_cached"] is False

        # 2. Second call: upstream fails
        def _failing_fetch(config, client=None):
            raise ts.UpstreamThingSpeakError(503, "ThingSpeak connection timed out")

        monkeypatch.setattr(ts, "fetch_feeds", _failing_fetch)
        resp2 = auth_client.get("/api/v1/thingspeak/latest")
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data2["is_cached"] is True
        assert data2["upstream_status"] == "unreachable"
        assert data2["channel_id"] == "244357"
        assert data2["entry_id"] == 122
        assert data2["values"]["pH"] == pytest.approx(7.40, abs=1e-3)
        assert "cached" in data2["hardware_status"].lower() or "offline" in data2["hardware_status"].lower()

    def test_upstream_failure_falls_back_to_database_cache(self, auth_client, monkeypatch):
        """When in-memory cache is empty but DB has persisted records, falls back to DB."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "77777")
        node_id = "thingspeak-77777"

        # Insert a persisted reading directly into DB
        db = next(get_db())
        NodeRepository.get_or_create(db, node_id, "ThingSpeak Channel 77777", "ThingSpeak")
        db_reading = SensorReading(
            node_id=node_id,
            ph=7.85,
            tds=180.0,
            turbidity=2.1,
            temperature=26.5,
            optical_colour_index=0.45,
            red=35,
            green=40,
            blue=45,
            source="THINGSPEAK",
            timestamp=datetime(2026, 10, 15, 8, 57, 8, tzinfo=timezone.utc),
        )
        db.add(db_reading)
        db.commit()

        # Clear in-memory cache
        forecast_api._thingspeak_feed_cache.clear()

        # Simulate upstream failure
        monkeypatch.setattr(
            ts, "fetch_feeds",
            lambda config, client=None: (_ for _ in ()).throw(ts.UpstreamThingSpeakError(504, "Gateway timeout"))
        )

        resp = auth_client.get("/api/v1/thingspeak/latest?channel_id=77777")
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_cached"] is True
        assert data["upstream_status"] == "unreachable"
        assert data["channel_id"] == "77777"
        assert data["values"]["pH"] == pytest.approx(7.85, abs=1e-3)
        assert data["values"]["TDS"] == pytest.approx(180.0, abs=1e-3)
        assert data["rgb"]["red"] == 35


class TestThingSpeakHistoryOffline:
    """Verifies history endpoint caching and offline fallback."""

    def test_history_returns_feeds_and_updates_cache(self, auth_client, monkeypatch):
        """History returns ascending feeds and saves to cache."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")

        test_feeds = [
            {
                "created_at": "2026-10-15T08:56:00Z",
                "entry_id": 120,
                "field1": "7.10",
                "field2": "140",
                "field3": "1.0",
                "field4": "24.0",
                "field5": "40",
                "field6": "30",
                "field7": "25",
                "field8": "0",
            },
            {
                "created_at": "2026-10-15T08:57:08Z",
                "entry_id": 121,
                "field1": "7.15",
                "field2": "142",
                "field3": "1.1",
                "field4": "24.1",
                "field5": "41",
                "field6": "31",
                "field7": "26",
                "field8": "0",
            },
        ]

        monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: list(test_feeds))

        resp = auth_client.get("/api/v1/thingspeak/history?limit=10")
        assert resp.status_code == 200
        body = resp.json()

        assert body["count"] == 2
        assert body["is_cached"] is False
        assert body["upstream_status"] == "reachable"
        assert body["readings"][0]["entry_id"] == 120
        assert body["readings"][1]["entry_id"] == 121

    def test_history_falls_back_to_cache_when_upstream_unreachable(self, auth_client, monkeypatch):
        """History falls back to cached entries when upstream fails."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")

        test_feeds = [
            {
                "created_at": "2026-10-15T08:56:00Z",
                "entry_id": 120,
                "field1": "7.10",
                "field2": "140",
                "field3": "1.0",
                "field4": "24.0",
                "field5": "40",
                "field6": "30",
                "field7": "25",
                "field8": "0",
            }
        ]

        # Populate cache
        monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: list(test_feeds))
        resp1 = auth_client.get("/api/v1/thingspeak/history?limit=10")
        assert resp1.status_code == 200

        # Now simulate network failure
        monkeypatch.setattr(
            ts, "fetch_feeds",
            lambda config, client=None: (_ for _ in ()).throw(ts.UpstreamThingSpeakError(503, "Host unreachable"))
        )

        resp2 = auth_client.get("/api/v1/thingspeak/history?limit=10")
        assert resp2.status_code == 200
        body2 = resp2.json()

        assert body2["is_cached"] is True
        assert body2["upstream_status"] == "unreachable"
        assert body2["count"] == 1
        assert body2["readings"][0]["entry_id"] == 120


class TestThingSpeakErrorHandling:
    """Verifies edge cases and error contracts."""

    def test_missing_channel_returns_helpful_503(self, auth_client, monkeypatch):
        """When no channel is configured, returns 503 explaining how to set HYDROGUARD_THINGSPEAK_CHANNEL_ID."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "")
        monkeypatch.setenv("THINGSPEAK_CHANNEL_ID", "")

        resp = auth_client.get("/api/v1/thingspeak/latest")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "HYDROGUARD_THINGSPEAK_CHANNEL_ID" in detail

    def test_empty_feeds_returns_502(self, auth_client, monkeypatch):
        """When upstream returns empty feed list and no cache exists, returns 502 without crashing."""
        monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "88888")
        monkeypatch.setattr(ts, "fetch_feeds", lambda config, client=None: [])

        resp = auth_client.get("/api/v1/thingspeak/latest?channel_id=88888")
        assert resp.status_code == 502
        assert "no observations" in resp.json()["detail"].lower()

    def test_explicit_query_param_channel_id_routing(self, auth_client, monkeypatch):
        """Passing ?channel_id=99999 queries the specified channel."""
        captured_config = []

        def _mock_fetch(config, client=None):
            captured_config.append(config)
            return [
                {
                    "created_at": "2026-10-23T12:00:00Z",
                    "entry_id": 1,
                    "field1": "7.0",
                    "field2": "200",
                    "field3": "1.0",
                    "field4": "25.0",
                }
            ]

        monkeypatch.setattr(ts, "fetch_feeds", _mock_fetch)

        resp = auth_client.get("/api/v1/thingspeak/latest?channel_id=99999")
        assert resp.status_code == 200
        assert captured_config[0].channel_id == "99999"
        assert resp.json()["channel_id"] == "99999"
