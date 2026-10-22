"""Unit and integration tests for real data pipeline, benchmarks, and model lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.auth import require_student_or_admin
from app.main import app
from ml.data.real_data_pipeline import (
    CORE_PARAMETERS,
    NextDayContract,
    load_real_observations_csv,
    perform_data_quality_audit,
    validate_and_clean_observations,
)
from ml.evaluation.benchmarks import compute_parameter_metrics, run_benchmark_suite
from ml.evaluation.model_lifecycle import (
    HorizonSupportStatus,
    ModelLifecycleState,
    evaluate_model_promotion,
)
from ml.services import thingspeak_service as ts

DEV_AUTH_HEADERS = {
    "X-Development-Role": "ADMIN",
    "X-Development-Email": "demo.admin@hydroguard.local",
    "X-Development-Token": "45aeee8ce44e752b482ca0c06d3f40e41d2f1c9eb918f6823497d4c789b4cf31",
}


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        require_student_or_admin,
        lambda: {"uid": "test-admin", "role": "ADMIN", "email": "demo.admin@hydroguard.local"},
    )
    from app.db.database import init_db
    init_db()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_student_or_admin, None)


def test_real_observations_csv_loading_and_shape():
    """Verify loading real ThingSpeak observations without fabrication."""
    df = load_real_observations_csv()
    assert len(df) == 122
    for param in CORE_PARAMETERS:
        assert param in df.columns
    assert "timestamp" in df.columns
    assert "entry_id" in df.columns
    # Ensure chronologically sorted
    assert df["timestamp"].is_monotonic_increasing


def test_validate_and_clean_preserves_dropouts_and_no_zero_fabrication():
    """Verify that dropouts are detected and not replaced with fabricated zeros."""
    df = load_real_observations_csv()
    cleaned, stats = validate_and_clean_observations(df)
    assert len(cleaned) == 122
    assert stats["duplicates_dropped"] == 0

    # Test set contains entry with pH=0.0 and temp=0.0 (bench sensor dropout)
    assert stats["dropouts"]["pH"] >= 1
    assert stats["dropouts"]["temperature"] >= 1

    # Verify physical validity rates
    assert stats["validity_rates"]["pH"] > 95.0
    assert stats["validity_rates"]["TDS"] == 100.0


def test_data_quality_audit_detects_all_gaps_and_temporal_coverage():
    """Verify gap quantification and temporal coverage calculation."""
    report = perform_data_quality_audit()
    assert report.total_raw_observations == 122
    assert report.large_gaps_count_gt_5min == 7
    assert report.large_gaps_count_gt_1hour == 5
    assert report.maximum_gap_hours > 80.0  # 89.29h gap

    # Total active measurement duration is ~71 mins
    assert 60.0 < report.total_active_measurement_minutes < 90.0
    # Over 7.2 days, 71 mins is < 1% coverage
    assert report.data_temporal_coverage_percent < 2.0

    # Verify that eligible next-day windows is exactly 0
    assert report.next_day_eligible_windows == 0
    assert report.next_day_eligibility_status == "INSUFFICIENT_DATA_UNAVAILABLE"


def test_next_day_contract_specifications():
    """Verify the formal contract for next-day water quality forecasting."""
    contract = NextDayContract()
    assert contract.nominal_horizon_hours == 24
    assert contract.cadence == "1D"
    assert contract.input_history_days == 7
    assert contract.min_daily_coverage_ratio == 0.70
    assert contract.max_allowed_intra_day_gap_hours == 2.0
    assert set(contract.parameters) == {"pH", "TDS", "turbidity", "temperature"}


def test_benchmark_metrics_computation():
    """Verify parameter metrics calculation produces non-negative MAE/RMSE."""
    actual = np.array([[7.0, 300.0, 2.0, 25.0], [7.2, 310.0, 2.5, 25.5]])
    pred = np.array([[7.1, 290.0, 2.2, 24.8], [7.0, 320.0, 2.3, 25.2]])
    m = compute_parameter_metrics(actual, pred)
    for p in CORE_PARAMETERS:
        assert m[p].MAE >= 0
        assert m[p].RMSE >= 0
        assert m[p].MAPE >= 0
    assert pytest.approx(m["pH"].MAE, 0.01) == 0.15


def test_benchmark_suite_execution_and_distribution_shift():
    """Verify benchmark execution on 122 observations and TDS shift diagnosis."""
    report = run_benchmark_suite()
    assert report["total_observations"] == 122
    assert report["split"]["train_samples"] == 85
    assert report["split"]["validation_samples"] == 18
    assert report["split"]["test_samples"] == 19

    models = report["models_evaluated"]
    assert "Persistence Baseline" in models
    assert "Moving Average Baseline (window=5)" in models
    assert "Four-Parameter Real LSTM" in models

    # Verify Persistence beats LSTM on TDS test set by vast margin
    pers_tds_mae = models["Persistence Baseline"]["test_metrics"]["TDS"]["MAE"]
    lstm_tds_mae = models["Four-Parameter Real LSTM"]["test_metrics"]["TDS"]["MAE"]
    assert pers_tds_mae < 1.0
    assert lstm_tds_mae > 100.0

    # Verify distribution shift diagnosis flags TDS as CRITICAL_SHIFT
    tds_shift = report["distribution_shift_analysis"]["TDS"]
    assert tds_shift["severity"] == "CRITICAL_SHIFT"
    assert tds_shift["normalized_mean_shift_in_training_sigmas"] > 0.8


def test_model_lifecycle_evaluation_and_promotion_gates():
    """Verify that models are evaluated against promotion gates and real LSTM is rejected for prod."""
    reg = evaluate_model_promotion()
    assert reg.next_day_forecast_status == HorizonSupportStatus.UNAVAILABLE_INSUFFICIENT_REAL_DATA.value

    real_model = next(m for m in reg.registered_models if m.model_name == "Four-Parameter Real LSTM")
    assert real_model.lifecycle_state == ModelLifecycleState.REJECTED.value
    assert real_model.approval_decision == "REJECTED_FOR_PRODUCTION"

    # Verify that at least one gate failed
    assert any(not g.passed for g in real_model.promotion_gates)

    ensemble = next(m for m in reg.registered_models if "Ensemble" in m.model_name)
    assert ensemble.lifecycle_state == ModelLifecycleState.EXPERIMENTAL.value
    assert ensemble.approval_decision == "APPROVED_AS_EXPERIMENTAL_FALLBACK_ONLY"


def test_real_data_audit_api_endpoint(auth_client):
    """Test GET /api/v1/real-data-audit returns 200 with structured audit."""
    resp = auth_client.get("/api/v1/real-data-audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "data_quality_audit" in data
    assert "model_lifecycle_registry" in data
    assert "model_benchmarks" in data
    assert data["data_quality_audit"]["total_raw_observations"] == 122
    assert data["model_lifecycle_registry"]["next_day_forecast_status"] == "UNAVAILABLE_INSUFFICIENT_REAL_DATA"


def test_forecast_thingspeak_response_includes_lifecycle_and_reason(auth_client, monkeypatch):
    """Test GET /api/v1/thingspeak/forecast includes lifecycle state and next-day reason."""
    feeds = [
        {
            "created_at": f"2026-10-15T08:{i:02d}:00Z",
            "entry_id": i + 1,
            "field1": "7.20",
            "field2": "300.0",
            "field3": "1.50",
            "field4": "25.0",
            "field5": "40",
            "field6": "29",
            "field7": "30",
            "field8": "1",
        }
        for i in range(30)
    ]
    monkeypatch.setattr(ts, "fetch_feeds", lambda config: feeds)
    monkeypatch.setenv("HYDROGUARD_THINGSPEAK_CHANNEL_ID", "244357")
    resp = auth_client.get("/api/v1/thingspeak/forecast?channel_id=244357")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["model_lifecycle_state"] == "EXPERIMENTAL"
    assert data["next_day_forecast_status"] == "UNAVAILABLE_INSUFFICIENT_REAL_DATA"
    assert "0.68%" in data["next_day_forecast_reason"]
    assert data["continuous_24h_windows"] == 0
