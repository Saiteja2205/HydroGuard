"""Contract checks for the explicitly simulated review dataset."""

import importlib.util
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = BACKEND_ROOT / "data" / "generate_development_water_quality_30day.py"
SPEC = importlib.util.spec_from_file_location("development_water_quality_30day", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def test_active_forecast_dataset_has_200_observations_and_explicit_provenance():
    dataset_path = BACKEND_ROOT / "data" / "development_water_quality_200_observations.csv"
    metadata_path = BACKEND_ROOT / "data" / "development_water_quality_200_observations.metadata.json"
    with dataset_path.open(encoding="utf-8", newline="") as source_file:
        rows = list(csv.DictReader(line for line in source_file if not line.lstrip().startswith("#")))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    timestamps = [row["timestamp"] for row in rows]
    assert len(rows) == 200
    assert timestamps == sorted(timestamps)
    assert metadata["observation_count"] == 200
    assert metadata["source"] == "SIMULATED_DEVELOPMENT"
    assert metadata["real_sensor_data"] is False
    assert metadata["parameters"] == ["pH", "TDS", "turbidity", "temperature", "optical_colour_index"]
    assert [int(200 * split) for split in (0.70, 0.85)] == [140, 170]

    evaluation_path = BACKEND_ROOT / "artifacts" / "results" / "five_parameter_evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    assert evaluation["dataset_size"] == 200
    assert evaluation["dataset_source"] == "SIMULATED_DEVELOPMENT"
    assert evaluation["split"] == {"train": 140, "validation": 30, "test": 30}
    assert evaluation["window_size"] == 30
    assert set(evaluation["training_results"]) == {"LSTM", "PatchTST", "TimeMixer"}
    assert all(model["status"] == "trained" for model in evaluation["training_results"].values())


def test_development_forecast_fallback_uses_validated_parameter_weights(monkeypatch):
    from app.api.forecast import _development_evaluation, _validated_development_weights

    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "development")
    evaluation = _development_evaluation()
    weights = _validated_development_weights(evaluation)

    assert weights is not None
    assert set(weights) == {"pH", "TDS", "turbidity", "temperature", "optical_colour_index"}
    assert all(abs(sum(parameter_weights.values()) - 1.0) < 1e-9 for parameter_weights in weights.values())
    assert weights["pH"]["TimeMixer"] > weights["pH"]["LSTM"]


def test_development_dataset_has_30_ordered_complete_five_parameter_rows():
    rows = GENERATOR.build_rows()

    assert len(rows) == 30
    assert rows[0]["timestamp"] == "2026-09-07T12:00:00Z"
    assert rows[-1]["timestamp"] == "2026-10-06T12:00:00Z"
    assert all(row["source"] == "SIMULATED_DEVELOPMENT" for row in rows)
    assert all(row["data_provenance"] == "SIMULATED_DEVELOPMENT" for row in rows)
    assert {row["condition"] for row in rows} == {"GOOD", "NORMAL", "DEGRADED"}

    for row in rows:
        assert 6.5 <= row["ph"] <= 8.5
        assert 0 <= row["tds"] <= 600
        assert 0 <= row["turbidity"] <= 10
        assert 15 <= row["temperature"] <= 30
        assert 0 <= row["optical_colour_index"] <= 1
        assert 0 < row["red"] < row["clear"] <= 65535
        assert 0 < row["green"] < row["clear"] <= 65535
        assert 0 < row["blue"] < row["clear"] <= 65535


def test_optical_colour_index_is_derived_from_raw_rgb_and_clear():
    rows = GENERATOR.build_rows()
    row = max(rows, key=lambda item: item["turbidity"])
    expected = 1 - (
        0.2126 * row["red"] + 0.7152 * row["green"] + 0.0722 * row["blue"]
    ) / row["clear"]

    assert abs(row["optical_colour_index"] - round(expected, 5)) < 0.00001


def test_naive_sqlite_timestamps_are_serialized_as_utc():
    from app.schemas.readings import serialize_utc_timestamp

    naive = datetime(2026, 10, 6, 12)
    aware = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)

    assert serialize_utc_timestamp(naive) == "2026-10-06T12:00:00Z"
    assert serialize_utc_timestamp(aware) == "2026-10-06T12:00:00Z"


def test_development_seed_is_idempotent_and_preserves_real_rows():
    from datetime import datetime, timezone

    from app.db.database import get_db_context, init_db
    from app.db.repositories import NodeRepository, SensorReadingRepository
    from app.db.seed import seed_development_dataset
    from sqlalchemy import func
    from app.db.models import SensorReading

    init_db()
    node_id = "seed_dataset_live_test"
    with get_db_context() as db:
        NodeRepository.get_or_create(db, node_id, "Seed test node", "Test")
        SensorReadingRepository.create(
            db,
            node_id=node_id,
            timestamp=datetime(2026, 10, 6, 13, tzinfo=timezone.utc),
            ph=7.1,
            tds=181,
            turbidity=1.2,
            temperature=23,
            red=10_000,
            green=10_000,
            blue=10_000,
            clear=11_000,
            optical_colour_index=0.1,
            source="REAL_SENSOR",
        )

        assert seed_development_dataset(db, node_id=node_id) == 200
        assert seed_development_dataset(db, node_id=node_id) == 0
        assert db.query(SensorReading).filter_by(node_id=node_id, source="REAL_SENSOR").count() == 1
        assert db.query(SensorReading).filter(
            SensorReading.node_id == node_id,
            func.upper(SensorReading.source) == "SIMULATED_DEVELOPMENT",
        ).count() == 200


def test_legacy_demo_seed_and_history_response_include_optical_colour(monkeypatch):
    from app.db.database import get_db_context, init_db
    from app.db.seed import seed_demo_data
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HYDROGUARD_ENVIRONMENT", "production")
    init_db()
    node_id = "legacy_optical_demo_test"
    with get_db_context() as db:
        assert seed_demo_data(db, node_id=node_id, days=24) == 24

    response = TestClient(app).get(f"/api/v1/nodes/{node_id}/readings/history?limit=100")
    assert response.status_code == 200, response.text
    readings = response.json()["readings"]
    assert len(readings) == 24
    assert all({"ph", "tds", "turbidity", "temperature", "optical_colour_index"} <= row.keys() for row in readings)
    assert all(row["optical_colour_index"] is not None for row in readings)
    assert len({row["optical_colour_index"] for row in readings}) > 1
