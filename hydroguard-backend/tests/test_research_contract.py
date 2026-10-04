"""Focused contract, provenance, and adaptive-weight regression tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.readings import ForecastReading, ForecastRequest, ReadingCreate
from ml.ensemble.weighting import calculate_parameter_weights, calculate_weights
from fastapi.testclient import TestClient
from app.core.auth import authenticated_principal
from app.main import app
from app.db.database import get_db_context, init_db
from app.db.repositories import (
    EnsembleWeightRepository,
    ForecastRepository,
    ModelErrorRepository,
    NodeRepository,
    SensorReadingRepository,
)
from app.services.error_tracking import ErrorTrackingService


def _reading(timestamp: datetime, **overrides) -> dict:
    value = {
        "timestamp": timestamp.isoformat(),
        "pH": 7.1,
        "TDS": 180,
        "turbidity": 1.2,
        "temperature": 22.0,
        "red": 120,
        "green": 130,
        "blue": 140,
        "clear": 390,
        "optical_colour_index": None,
        "source": "HISTORICAL_DATA",
    }
    value.update(overrides)
    return value


def test_active_reading_contract_preserves_raw_colour_and_rejects_legacy_fields():
    reading = ReadingCreate(
        node_id="test_node",
        timestamp=datetime.now(timezone.utc),
        ph=7.1,
        tds=180,
        turbidity=1.2,
        temperature=22,
        red=120,
        green=130,
        blue=140,
        clear=390,
        optical_colour_index=None,
        source="DEMO",
    )
    assert (reading.red, reading.green, reading.blue, reading.clear) == (120, 130, 140, 390)
    payload = reading.model_dump()
    for deprecated in ("ec", "do", "flow_rate", "flowRate"):
        with pytest.raises(ValidationError):
            ReadingCreate(**{**payload, deprecated: 1})


def test_forecast_request_rejects_duplicate_unordered_naive_and_future_timestamps():
    base = datetime.now(timezone.utc) - timedelta(days=2)
    valid = [_reading(base), _reading(base + timedelta(hours=1))]
    ForecastRequest(node_id="test_node", readings=valid)

    cases = [
        [valid[0], valid[0]],
        [valid[1], valid[0]],
        [_reading(datetime.now()), valid[1]],
        [valid[0], _reading(datetime.now(timezone.utc) + timedelta(days=1))],
    ]
    for readings in cases:
        with pytest.raises(ValidationError):
            ForecastRequest(node_id="test_node", readings=readings)


def test_forecast_reading_rejects_missing_and_invalid_sensor_values():
    valid = _reading(datetime.now(timezone.utc) - timedelta(days=1))
    for invalid in (
        {key: value for key, value in valid.items() if key != "temperature"},
        {**valid, "pH": 15},
        {**valid, "source": "MIXED"},
        {**valid, "flow_rate": 2},
    ):
        with pytest.raises(ValidationError):
            ForecastReading(**invalid)


def test_error_weights_are_stable_parameter_specific_and_reward_lower_error():
    weights = calculate_weights([0.0, 1e-300, 1e300])
    assert all(value >= 0 for value in weights)
    assert sum(weights) == pytest.approx(1.0)
    ranked = calculate_weights([1.0, 2.0, 3.0])
    assert ranked[0] > ranked[1] > ranked[2]

    by_parameter = calculate_parameter_weights({
        "LSTM": {"pH": 1.0, "TDS": 9.0},
        "PatchTST": {"pH": 5.0, "TDS": 1.0},
        "TimeMixer": {"pH": 8.0, "TDS": 4.0},
    })
    assert by_parameter["pH"]["LSTM"] > by_parameter["pH"]["PatchTST"]
    assert by_parameter["TDS"]["PatchTST"] > by_parameter["TDS"]["LSTM"]


def test_error_weights_reject_nan_and_negative_scores():
    for errors in ([float("nan"), 1.0], [-1.0, 2.0]):
        with pytest.raises(ValueError):
            calculate_weights(errors)


def test_actual_observation_matches_forecast_and_persists_errors_and_weights():
    init_db()
    node_id = f"contract_{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    predictions = {
        "pH": 7.0,
        "TDS": 180.0,
        "turbidity": 1.0,
        "temperature": 22.0,
    }
    model_predictions = {
        "LSTM": predictions,
        "PatchTST": {**predictions, "pH": 7.1},
        "TimeMixer": {**predictions, "TDS": 190.0},
    }
    equal_weights = {
        parameter: {"LSTM": 1 / 3, "PatchTST": 1 / 3, "TimeMixer": 1 / 3}
        for parameter in ("pH", "TDS", "turbidity", "temperature")
    }

    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Contract node", "Test")
        forecast = ForecastRepository.create(
            db,
            node_id,
            now,
            model_predictions["LSTM"],
            model_predictions["PatchTST"],
            model_predictions["TimeMixer"],
            predictions,
            equal_weights,
            data_source="DEMO",
        )
        actual = SensorReadingRepository.create(
            db,
            node_id,
            now,
            ph=7.2,
            tds=181.0,
            turbidity=1.1,
            temperature=22.5,
            red=11,
            green=12,
            blue=13,
            clear=36,
            source="DEMO",
        )
        assert ErrorTrackingService.evaluate_actual_reading(db, actual) == 12
        errors = ModelErrorRepository.get_by_node(db, node_id)
        assert len(errors) == 12
        assert {row.data_source for row in errors} == {"DEMO"}
        assert {row.actual_timestamp.date() for row in errors} == {now.date()}
        assert {row.parameter for row in errors} == {"pH", "TDS", "turbidity", "temperature"}
        assert EnsembleWeightRepository.get_by_node(db, node_id, "DEMO")
        assert ErrorTrackingService.evaluate_actual_reading(db, actual) == 0


def test_research_csv_requires_admin_and_preserves_empty_metrics(monkeypatch):
    client = TestClient(app)
    assert client.get("/api/v1/research/export.csv").status_code == 401
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: {"uid": "research-admin", "role": "ADMIN"})
    response = client.get("/api/v1/research/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    header = response.text.splitlines()[0]
    assert "red" in header and "clear" in header and "optical_colour_index" in header
    assert "forecast_horizon_hours" in header and "mae" in header and "ensemble_weight" in header
