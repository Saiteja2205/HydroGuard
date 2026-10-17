"""Cached multi-model inference for HydroGuard.

Loads LSTM, PatchTST and TimeMixer once, runs them over a raw
``(window, 5)`` observation window, and returns physical-unit forecasts
including the weighted ensemble.

This is deliberately separate from :mod:`ml.services.forecast_service`, which
couples model loading to a database-backed adaptive-ensemble workflow. This
module is the minimal, dependency-light path a cloud deployment needs:

* Checkpoints load **once** onto CPU and are cached on the instance, so a
  cold start pays the cost and every later request reuses the weights.
* Scaling uses the ``scaler_mean`` / ``scaler_std`` stored *inside each
  checkpoint* -- the constants the weights were actually trained against.
  Fitting a scaler to the incoming request would silently rescale the input
  into a different distribution than the model expects.
* The parameter order is taken from the checkpoint, not assumed, and a
  checkpoint whose parameter list or feature count disagrees with the active
  contract is rejected loudly rather than being coerced into place.

Provenance is carried through, not stripped: every result reports which
checkpoint files were used and what dataset they were trained on. The shipped
checkpoints were trained on ``SIMULATED_DEVELOPMENT`` data, and that stays
visible in the output so a caller never mistakes these forecasts for
certified measurements.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch

from ml.data.validator import PARAMETERS
from ml.ensemble.weighting import WeightingConfig, calculate_parameter_weights

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT_DIR = _BACKEND_ROOT / "artifacts" / "checkpoints"

MODEL_FILENAMES: dict[str, str] = {
    "LSTM": "lstm_water_quality_5param_v1.pt",
    "PatchTST": "patchtst_water_quality_5param_v1.pt",
    "TimeMixer": "timemixer_water_quality_5param_v1.pt",
}

# Canonical key used in JSON responses. The spec names the models in lowercase.
MODEL_RESPONSE_KEYS: dict[str, str] = {
    "LSTM": "lstm",
    "PatchTST": "patchtst",
    "TimeMixer": "timemixer",
}

DEFAULT_WINDOW_SIZE = 30


class InferenceError(RuntimeError):
    """Base class for inference failures."""


class CheckpointMissing(InferenceError):
    """A required checkpoint file is not present on disk."""


class CheckpointIncompatible(InferenceError):
    """A checkpoint does not match the active five-parameter contract."""


@dataclass(frozen=True)
class InferenceResult:
    """Forecasts for one window, in physical units.

    ``model_forecasts`` keys are the response names (``lstm`` / ``patchtst`` /
    ``timemixer``); ``ensemble`` is the weighted combination. ``weights`` is
    ``{parameter: {model: weight}}`` so a caller can show exactly how much each
    model contributed to each parameter.
    """

    latest_values: Mapping[str, float]
    model_forecasts: Mapping[str, Mapping[str, float]]
    ensemble: Mapping[str, float]
    weights: Mapping[str, Mapping[str, float]]
    parameters: tuple[str, ...]
    checkpoint_versions: Mapping[str, str]
    training_dataset_source: str
    real_sensor_data: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "latest_values": dict(self.latest_values),
            "forecast": {**dict(self.model_forecasts), "ensemble": dict(self.ensemble)},
            "weights": {p: dict(m) for p, m in self.weights.items()},
            "parameters": list(self.parameters),
            "checkpoint_versions": dict(self.checkpoint_versions),
            "training_dataset_source": self.training_dataset_source,
            "real_sensor_data": self.real_sensor_data,
        }


@dataclass
class _LoadedModel:
    """One loaded checkpoint: the module, its scaler and its provenance."""

    name: str
    module: torch.nn.Module
    scaler_mean: np.ndarray
    scaler_std: np.ndarray
    parameters: tuple[str, ...]
    version: str
    training_dataset_source: str
    real_sensor_data: bool


class InferenceService:
    """Loads the three checkpoints once and forecasts raw observation windows.

    Thread-safe: :meth:`load` takes a lock so concurrent first requests cannot
    load the checkpoints twice. Once loaded, :meth:`forecast` is read-only with
    respect to model state, so it can serve requests from many threads.
    """

    def __init__(
        self,
        checkpoint_dir: str | Path | None = None,
        device: str = "cpu",
        window_size: int = DEFAULT_WINDOW_SIZE,
        parameters: Sequence[str] = PARAMETERS,
        ensemble_config: WeightingConfig | None = None,
    ) -> None:
        self.checkpoint_dir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)
        # CPU is the deliberate default: cloud free tiers are CPU-only, and a
        # CUDA build pulls multi-gigabyte wheels that exceed their disk limits.
        self.device = torch.device(device)
        self.window_size = int(window_size)
        self.parameters = tuple(parameters)
        self.ensemble_config = ensemble_config or WeightingConfig()
        self._models: dict[str, _LoadedModel] = {}
        self._loaded = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def status(self) -> dict[str, bool]:
        """Per-model load state, for a health check that must not load anything."""
        return {MODEL_RESPONSE_KEYS[name]: name in self._models for name in MODEL_FILENAMES}

    def load(self) -> None:
        """Load all checkpoints. Idempotent and safe to call concurrently."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            loaded: dict[str, _LoadedModel] = {}
            try:
                for name in MODEL_FILENAMES:
                    loaded[name] = self._load_one(name)
            except Exception:
                # Leave the service unloaded rather than half-loaded, so a
                # retry starts clean instead of mixing old and new weights.
                self._models = {}
                self._loaded = False
                raise
            self._models = loaded
            self._loaded = True

    def _checkpoint_path(self, name: str) -> Path:
        path = self.checkpoint_dir / MODEL_FILENAMES[name]
        if not path.is_file():
            raise CheckpointMissing(
                f"Checkpoint for {name} not found at {path}. "
                "Train the models with ml/training/ before serving forecasts."
            )
        return path

    def _load_one(self, name: str) -> _LoadedModel:
        path = self._checkpoint_path(name)
        # weights_only=False is required because these first-party checkpoints
        # store a config dict, a parameter list and scaler arrays alongside the
        # state dict. The files are trusted and git-tracked in this repository.
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        if not isinstance(checkpoint, Mapping):
            raise CheckpointIncompatible(f"{path.name} is not a checkpoint mapping.")

        state_dict = checkpoint.get("model_state_dict")
        config = checkpoint.get("config") or {}
        if not isinstance(state_dict, Mapping) or not isinstance(config, Mapping):
            raise CheckpointIncompatible(f"{path.name} is missing model_state_dict or config.")

        module = self._build_module(name, config)
        try:
            module.load_state_dict(state_dict)
        except RuntimeError as exc:
            raise CheckpointIncompatible(
                f"{path.name} weights do not match the {name} architecture: {exc}"
            ) from exc
        module.to(self.device)
        module.eval()

        ck_parameters = tuple(str(p) for p in (checkpoint.get("parameters") or ()))
        if ck_parameters and ck_parameters != self.parameters:
            raise CheckpointIncompatible(
                f"{path.name} was trained on {ck_parameters}, but this service "
                f"expects {self.parameters}. Refusing to mix parameter contracts."
            )

        # Prefer the checkpoint's own feature_count, then the config's
        # input_size, then the active contract. The previous form called len()
        # on config["input_size"], which is an int, so it always raised.
        feature_count = int(
            checkpoint.get("feature_count", config.get("input_size", len(self.parameters)))
        )
        if feature_count != len(self.parameters):
            raise CheckpointIncompatible(
                f"{path.name} has {feature_count} features; expected {len(self.parameters)}."
            )

        mean, std = self._extract_scaler(checkpoint, path.name)

        return _LoadedModel(
            name=name,
            module=module,
            scaler_mean=mean,
            scaler_std=std,
            parameters=ck_parameters or self.parameters,
            version=str(checkpoint.get("model_version") or path.name),
            training_dataset_source=str(checkpoint.get("dataset_source") or "unknown"),
            real_sensor_data=bool(checkpoint.get("real_sensor_data", False)),
        )

    @staticmethod
    def _build_module(name: str, config: Mapping[str, Any]) -> torch.nn.Module:
        """Construct the architecture named by the checkpoint's own config.

        Defaults mirror the architectures in :mod:`ml.models`, but every value
        the checkpoint recorded wins, so a retrained model with different
        widths loads correctly instead of failing on a shape mismatch.
        """
        if name == "LSTM":
            from ml.models.lstm_model import LSTMModel

            return LSTMModel(
                input_size=int(config.get("input_size", 5)),
                hidden_size=int(config.get("hidden_size", 64)),
                num_layers=int(config.get("num_layers", 2)),
                dropout=float(config.get("dropout", 0.2)),
                output_size=int(config.get("output_size", 5)),
            )
        if name == "PatchTST":
            from ml.models.patchtst_model import PatchTST

            return PatchTST(
                input_size=int(config.get("input_size", 5)),
                context_length=int(config.get("context_length", 30)),
                patch_length=int(config.get("patch_length", 5)),
                stride=int(config.get("stride", 5)),
                d_model=int(config.get("d_model", 64)),
                num_heads=int(config.get("num_heads", 4)),
                num_layers=int(config.get("num_layers", 2)),
                dropout=float(config.get("dropout", 0.1)),
                output_size=int(config.get("output_size", 5)),
            )
        if name == "TimeMixer":
            from ml.models.timemixer_model import TimeMixer

            return TimeMixer(
                input_size=int(config.get("input_size", 5)),
                context_length=int(config.get("context_length", 30)),
                hidden_size=int(config.get("hidden_size", 64)),
                num_scales=int(config.get("num_scales", 3)),
                num_mixing_layers=int(config.get("num_mixing_layers", 2)),
                dropout=float(config.get("dropout", 0.1)),
                output_size=int(config.get("output_size", 5)),
            )
        raise CheckpointIncompatible(f"Unknown model name: {name}")

    @staticmethod
    def _extract_scaler(checkpoint: Mapping[str, Any], filename: str) -> tuple[np.ndarray, np.ndarray]:
        """Read the training scaler stored in the checkpoint.

        These constants are the ones the weights were fitted against, so they
        are mandatory. A checkpoint without them would need refitting, which
        would change every forecast, so it is rejected instead.
        """
        mean_raw = checkpoint.get("scaler_mean")
        std_raw = checkpoint.get("scaler_std")
        if mean_raw is None or std_raw is None:
            raise CheckpointIncompatible(
                f"{filename} has no scaler_mean/scaler_std. A checkpoint without "
                "its training scaler cannot be used for inference."
            )
        mean = np.asarray(mean_raw, dtype=np.float32)
        std = np.asarray(std_raw, dtype=np.float32)
        if mean.shape != std.shape:
            raise CheckpointIncompatible(f"{filename} scaler mean/std shapes disagree.")
        if np.any(std == 0) or not np.isfinite(std).all() or not np.isfinite(mean).all():
            raise CheckpointIncompatible(f"{filename} has a degenerate scaler (zero or non-finite).")
        return mean, std

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    def _validate_window(self, window: np.ndarray) -> np.ndarray:
        array = np.asarray(window, dtype=np.float32)
        expected = (self.window_size, len(self.parameters))
        if array.shape != expected:
            raise ValueError(
                f"Expected an observation window of shape {expected}, got {array.shape}."
            )
        if not np.isfinite(array).all():
            raise ValueError("The observation window contains missing or non-finite values.")
        return array

    def _run_model(self, model: _LoadedModel, scaled: np.ndarray) -> dict[str, float]:
        batch = torch.from_numpy(scaled[np.newaxis, ...]).float().to(self.device)
        with torch.no_grad():
            output = model.module(batch)
        scaled_prediction = output.detach().cpu().numpy()[0]
        # Inverse transform: physical = scaled * std + mean, using the same
        # constants that scaled the input, so the round trip is consistent.
        physical = scaled_prediction * model.scaler_std + model.scaler_mean
        return {param: float(value) for param, value in zip(self.parameters, physical)}

    def _equal_weights(self) -> dict[str, dict[str, float]]:
        # Keyed by the response names (lstm/patchtst/timemixer) because these
        # dicts are read alongside model_forecasts, which uses those keys.
        names = tuple(MODEL_RESPONSE_KEYS.values())
        equal = 1.0 / len(names)
        return {param: {name: equal for name in names} for param in self.parameters}

    def _resolve_weights(self, weights: Mapping[str, Mapping[str, float]] | None) -> dict[str, dict[str, float]]:
        """Validate supplied weights, or fall back to equal weighting.

        Per-parameter weights must cover every model with finite, non-negative
        values that do not all vanish. Anything else would silently produce a
        lopsided or NaN forecast, so equal weights are used instead. Keys are
        the response model names, matching ``model_forecasts``.
        """
        if not weights:
            return self._equal_weights()
        names = tuple(MODEL_RESPONSE_KEYS.values())
        resolved: dict[str, dict[str, float]] = {}
        for param in self.parameters:
            entry = weights.get(param)
            if not isinstance(entry, Mapping) or set(entry) != set(names):
                return self._equal_weights()
            numeric: dict[str, float] = {}
            for name in names:
                try:
                    value = float(entry[name])
                except (TypeError, ValueError):
                    return self._equal_weights()
                if not np.isfinite(value) or value < 0:
                    return self._equal_weights()
                numeric[name] = value
            total = sum(numeric.values())
            if total <= 0:
                return self._equal_weights()
            resolved[param] = {name: value / total for name, value in numeric.items()}
        return resolved

    def weights_from_errors(
        self,
        model_errors: Mapping[str, Mapping[str, Mapping[str, float]]],
    ) -> dict[str, dict[str, float]]:
        """Derive per-parameter inverse-error weights from observed errors.

        ``model_errors`` is ``{model: {parameter: error}}`` using the response
        model names (lstm/patchtst/timemixer), matching what the API emits.
        The weighting math in :func:`ml.ensemble.weighting.calculate_parameter_weights`
        is name-agnostic, so errors are passed through under the response
        names and the returned weights are also response-keyed -- consistent
        with :meth:`_resolve_weights`.
        """
        response_names = tuple(MODEL_RESPONSE_KEYS.values())
        errors: dict[str, dict[str, float]] = {}
        for name in response_names:
            entry = model_errors.get(name)
            if not isinstance(entry, Mapping):
                return self._equal_weights()
            try:
                errors[name] = {p: float(entry[p]) for p in self.parameters}
            except (KeyError, TypeError, ValueError):
                return self._equal_weights()
        if len(errors) != len(response_names):
            return self._equal_weights()
        return calculate_parameter_weights(errors, self.ensemble_config)

    def forecast(
        self,
        window: np.ndarray,
        weights: Mapping[str, Mapping[str, float]] | None = None,
    ) -> InferenceResult:
        """Forecast the next step for a raw ``(window, 5)`` observation window.

        The window is in **physical units** (raw sensor values); scaling,
        inference, inverse scaling and ensembling all happen here.
        """
        if not self._loaded:
            self.load()

        array = self._validate_window(window)

        model_forecasts: dict[str, dict[str, float]] = {}
        checkpoint_versions: dict[str, str] = {}
        dataset_sources: set[str] = set()
        real_flags: set[bool] = set()

        for name, model in self._models.items():
            scaled = (array - model.scaler_mean) / model.scaler_std
            model_forecasts[MODEL_RESPONSE_KEYS[name]] = self._run_model(model, scaled.astype(np.float32))
            checkpoint_versions[MODEL_RESPONSE_KEYS[name]] = model.version
            dataset_sources.add(model.training_dataset_source)
            real_flags.add(model.real_sensor_data)

        resolved_weights = self._resolve_weights(weights)

        # model_forecasts and resolved_weights are keyed by the response names
        # (lstm/patchtst/timemixer), so iterate those values -- not the
        # canonical keys of MODEL_RESPONSE_KEYS.
        response_keys = tuple(MODEL_RESPONSE_KEYS.values())

        ensemble: dict[str, float] = {}
        for param in self.parameters:
            ensemble[param] = sum(
                model_forecasts[key][param] * resolved_weights[param][key]
                for key in response_keys
            )

        latest = {param: float(array[-1, index]) for index, param in enumerate(self.parameters)}

        return InferenceResult(
            latest_values=latest,
            model_forecasts=model_forecasts,
            ensemble=ensemble,
            weights=resolved_weights,
            parameters=self.parameters,
            checkpoint_versions=checkpoint_versions,
            # If the checkpoints ever disagree, the least reassuring label wins
            # so a mixed set cannot be presented as fully real-sensor trained.
            training_dataset_source=(
                dataset_sources.pop() if len(dataset_sources) == 1 else "mixed"
            ),
            real_sensor_data=bool(real_flags) and all(real_flags),
        )


def load_configured_checkpoint_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the checkpoint directory from the environment, if overridden."""
    env = os.environ if environ is None else environ
    override = (env.get("HYDROGUARD_CHECKPOINT_DIR") or "").strip()
    return Path(override) if override else DEFAULT_CHECKPOINT_DIR


_SERVICE: InferenceService | None = None
_SERVICE_LOCK = threading.Lock()


def get_inference_service() -> InferenceService:
    """Return the process-wide inference service, creating it on first use.

    The instance is shared so checkpoints load once per process instead of
    once per request. Loading the weights still happens lazily on the first
    forecast, keeping the health endpoint cheap.
    """
    global _SERVICE
    if _SERVICE is None:
        with _SERVICE_LOCK:
            if _SERVICE is None:
                _SERVICE = InferenceService(checkpoint_dir=load_configured_checkpoint_dir())
    return _SERVICE


def reset_inference_service() -> None:
    """Drop the cached service. Intended for tests that change configuration."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = None
