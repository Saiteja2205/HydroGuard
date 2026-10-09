"""Forecast source selection must be development-only for stored synthetic data."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.forecast import _forecast_history, generate_forecast
from app.db.repositories import NodeRepository
from app.schemas.readings import ForecastRequest


def _reading(source: str = "REAL_SENSOR") -> dict:
    return {
        "timestamp": "2026-10-05T12:00:00Z",
        "pH": 7.0,
        "TDS": 200.0,
        "turbidity": 1.0,
        "temperature": 22.0,
        "red": 120,
        "green": 140,
        "blue": 110,
        "clear": 300,
        "optical_colour_index": 0.12,
        "source": source,
    }


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def order_by(self, *_columns):
        return self

    def all(self):
        return self.rows


def test_development_request_uses_stored_development_rows_with_provenance(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    row = SimpleNamespace(
        timestamp=datetime(2026, 10, 5, 12, tzinfo=timezone.utc),
        ph=7.0,
        tds=200.0,
        turbidity=1.0,
        temperature=22.0,
        red=120,
        green=140,
        blue=110,
        clear=300,
        optical_colour_index=0.12,
        calibration_id=None,
        source="SIMULATED_DEVELOPMENT",
    )
    db = SimpleNamespace(query=lambda _model: _Query([row]))
    request = ForecastRequest(node_id="node_overhead_a")

    readings, source = _forecast_history(request, db)

    assert source == "SIMULATED_DEVELOPMENT"
    assert len(readings) == 1
    assert readings[0].source == "SIMULATED_DEVELOPMENT"
    assert readings[0].optical_colour_index == 0.12
    assert readings[0].red == 120


def test_development_stored_selection_rejects_a_real_sensor_source(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    request = ForecastRequest(node_id="node_overhead_a", source="REAL_SENSOR")

    with pytest.raises(HTTPException) as error:
        _forecast_history(request, SimpleNamespace())

    assert error.value.status_code == 422


def test_production_requires_real_timestamped_request_observations(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")

    with pytest.raises(HTTPException) as missing:
        _forecast_history(ForecastRequest(node_id="node_overhead_a"), SimpleNamespace())
    assert missing.value.status_code == 422

    simulated = ForecastRequest(node_id="node_overhead_a", readings=[_reading("SIMULATED_DEVELOPMENT")])
    with pytest.raises(HTTPException) as rejected:
        _forecast_history(simulated, SimpleNamespace())
    assert rejected.value.status_code == 422


def test_production_accepts_real_timestamped_request_observations(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")
    request = ForecastRequest(node_id="node_overhead_a", readings=[_reading()])

    readings, source = _forecast_history(request, SimpleNamespace())

    assert source == "REAL_SENSOR"
    assert len(readings) == 1


def test_production_forecast_route_rejects_a_full_simulated_history(monkeypatch):
    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")
    monkeypatch.setattr(NodeRepository, "get_by_node_id", lambda *_args: object())
    first_day = datetime(2026, 9, 1, tzinfo=timezone.utc)
    readings = []
    for index in range(30):
        observation = _reading("SIMULATED_DEVELOPMENT")
        observation["timestamp"] = (first_day + timedelta(days=index)).isoformat()
        readings.append(observation)
    request = ForecastRequest(node_id="node_overhead_a", readings=readings)

    with pytest.raises(HTTPException) as error:
        generate_forecast(request, db=SimpleNamespace(), principal={"role": "STUDENT"})

    assert error.value.status_code == 422
    assert "Production forecasts require" in error.value.detail
