"""Tests for the cached multi-model inference service.

These load the three real checkpoints from ``artifacts/checkpoints`` and run
genuine forward passes on CPU. They assert structure, scaling round-trips and
honest provenance -- never a specific numeric forecast, because the shipped
weights are development-trained and a pinned number would imply a precision
the models do not have.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.services.inference_service import (  # noqa: E402
    CheckpointIncompatible,
    CheckpointMissing,
    InferenceService,
    MODEL_RESPONSE_KEYS,
    get_inference_service,
    load_configured_checkpoint_dir,
    reset_inference_service,
)

PARAMS = ("pH", "TDS", "turbidity", "temperature", "optical_colour_index")
RESPONSE_KEYS = tuple(MODEL_RESPONSE_KEYS.values())


def _window(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.column_stack(
        [
            rng.normal(7.2, 0.13, 30),
            rng.normal(295, 9.5, 30),
            rng.normal(1.25, 0.22, 30),
            rng.normal(23, 0.97, 30),
            rng.normal(0.56, 0.025, 30),
        ]
    ).astype(np.float32)


@pytest.fixture(scope="module")
def service() -> InferenceService:
    svc = InferenceService()
    svc.load()
    return svc


class TestLoading:
    def test_all_three_models_load(self, service):
        assert all(service.status().values())
        assert set(service.status()) == set(RESPONSE_KEYS)

    def test_status_reports_not_loaded_before_load(self):
        reset_inference_service()
        svc = InferenceService()
        assert not any(svc.status().values())

    def test_load_is_idempotent(self, service):
        first = id(service._models["LSTM"].module)
        service.load()
        assert id(service._models["LSTM"].module) == first

    def test_missing_checkpoint_dir_raises(self):
        svc = InferenceService(checkpoint_dir="/nonexistent/dir")
        with pytest.raises(CheckpointMissing):
            svc.load()

    def test_checkpoints_are_simulated_development(self, service):
        # The shipped weights were trained on a 200-row simulated dataset. If
        # this ever changes to real data the assertion should be updated
        # deliberately, not relaxed away.
        for name, model in service._models.items():
            assert model.training_dataset_source == "SIMULATED_DEVELOPMENT", name
            assert model.real_sensor_data is False, name

    def test_scaler_came_from_the_checkpoint(self, service):
        model = service._models["LSTM"]
        assert model.scaler_mean.shape == (5,)
        assert model.scaler_std.shape == (5,)
        assert np.all(model.scaler_std > 0)
        # Trained pH sits near neutral, not at zero.
        assert 6.5 < model.scaler_mean[0] < 8.0


class TestForecast:
    def test_returns_every_model_and_ensemble(self, service):
        result = service.forecast(_window())
        assert set(result.model_forecasts) == set(RESPONSE_KEYS)
        assert set(result.ensemble) == set(PARAMS)

    def test_values_are_physical_not_scaled(self, service):
        result = service.forecast(_window())
        # Scaled values would sit near 0; physical pH must be near 7.
        assert 0.0 < result.ensemble["pH"] < 14.0
        assert result.ensemble["TDS"] > 10.0

    def test_ensemble_is_the_weighted_mean(self, service):
        result = service.forecast(_window())
        for param in PARAMS:
            manual = sum(
                result.model_forecasts[key][param] * result.weights[param][key]
                for key in RESPONSE_KEYS
            )
            assert result.ensemble[param] == pytest.approx(manual, abs=1e-5)

    def test_weights_sum_to_one_per_parameter(self, service):
        result = service.forecast(_window())
        for param in PARAMS:
            assert sum(result.weights[param].values()) == pytest.approx(1.0, abs=1e-6)

    def test_latest_values_match_the_last_row(self, service):
        window = _window(11)
        result = service.forecast(window)
        assert result.latest_values["pH"] == pytest.approx(float(window[-1, 0]))
        assert result.latest_values["TDS"] == pytest.approx(float(window[-1, 1]))

    def test_is_deterministic(self, service):
        window = _window(3)
        a = service.forecast(window)
        b = service.forecast(window)
        assert a.ensemble == b.ensemble

    def test_forecast_is_finite(self, service):
        result = service.forecast(_window())
        for model_vals in result.model_forecasts.values():
            assert all(np.isfinite(v) for v in model_vals.values())
        assert all(np.isfinite(v) for v in result.ensemble.values())


class TestWeights:
    def test_custom_weights_are_respected(self, service):
        window = _window(5)
        weights = {p: {"lstm": 1.0, "patchtst": 0.0, "timemixer": 0.0} for p in PARAMS}
        result = service.forecast(window, weights=weights)
        assert result.ensemble["pH"] == pytest.approx(result.model_forecasts["lstm"]["pH"])

    def test_negative_weights_fall_back_to_equal(self, service):
        result = service.forecast(_window(), weights={"pH": {"lstm": -5}})
        for key in RESPONSE_KEYS:
            assert result.weights["pH"][key] == pytest.approx(1 / 3)

    def test_wrong_model_set_falls_back_to_equal(self, service):
        result = service.forecast(_window(), weights={"pH": {"lstm": 1.0}})
        assert result.weights["pH"]["lstm"] == pytest.approx(1 / 3)

    def test_all_zero_weights_fall_back_to_equal(self, service):
        weights = {p: {"lstm": 0.0, "patchtst": 0.0, "timemixer": 0.0} for p in PARAMS}
        result = service.forecast(_window(), weights=weights)
        assert result.weights["pH"]["lstm"] == pytest.approx(1 / 3)

    def test_nan_weight_falls_back_to_equal(self, service):
        result = service.forecast(_window(), weights={"pH": {"lstm": float("nan")}})
        assert result.weights["pH"]["lstm"] == pytest.approx(1 / 3)

    def test_weights_from_errors_prefers_lower_error(self, service):
        errors = {
            "lstm": {p: 0.1 for p in PARAMS},
            "patchtst": {p: 1.0 for p in PARAMS},
            "timemixer": {p: 1.0 for p in PARAMS},
        }
        weights = service.weights_from_errors(errors)
        assert weights["pH"]["lstm"] > weights["pH"]["patchtst"]

    def test_weights_from_errors_missing_model_falls_back(self, service):
        weights = service.weights_from_errors({"lstm": {p: 0.1 for p in PARAMS}})
        assert weights["pH"]["lstm"] == pytest.approx(1 / 3)


class TestInputValidation:
    def test_wrong_shape_rejected(self, service):
        with pytest.raises(ValueError):
            service.forecast(np.ones((10, 5), dtype=np.float32))

    def test_wrong_feature_count_rejected(self, service):
        with pytest.raises(ValueError):
            service.forecast(np.ones((30, 4), dtype=np.float32))

    def test_nan_window_rejected(self, service):
        with pytest.raises(ValueError):
            service.forecast(np.full((30, 5), np.nan, dtype=np.float32))

    def test_inf_window_rejected(self, service):
        with pytest.raises(ValueError):
            service.forecast(np.full((30, 5), np.inf, dtype=np.float32))


class TestProvenance:
    def test_result_labels_training_source(self, service):
        result = service.forecast(_window())
        assert result.training_dataset_source == "SIMULATED_DEVELOPMENT"
        assert result.real_sensor_data is False

    def test_checkpoint_versions_are_reported(self, service):
        result = service.forecast(_window())
        assert set(result.checkpoint_versions) == set(RESPONSE_KEYS)
        assert all(v for v in result.checkpoint_versions.values())


class TestSingleton:
    def test_get_returns_shared_instance(self):
        reset_inference_service()
        a = get_inference_service()
        b = get_inference_service()
        assert a is b

    def test_reset_clears_the_cache(self):
        reset_inference_service()
        a = get_inference_service()
        reset_inference_service()
        b = get_inference_service()
        assert a is not b

    def test_checkpoint_dir_env_override(self, monkeypatch):
        monkeypatch.setenv("HYDROGUARD_CHECKPOINT_DIR", "/tmp/custom-ckpts")
        assert load_configured_checkpoint_dir() == Path("/tmp/custom-ckpts")

    def test_checkpoint_dir_defaults_to_artifacts(self):
        reset_inference_service()
        resolved = load_configured_checkpoint_dir({})
        assert resolved.name == "checkpoints"
        assert resolved.parent.name == "artifacts"
