"""Sensor data quality and physical validation rules for HydroGuard.

Provides parameter-specific validation, sensor dropout detection, physical boundary
enforcement, and quality classification for water-quality observations.

Physical parameters:
- pH: Physical aqueous range [0.0, 14.0]. Values <= 0.05 represent 0V ADC probe dropouts.
- TDS: Total Dissolved Solids in ppm (mg/L). Non-negative. TDS = 0.0 in natural/tank water
  indicates an open-circuit / disconnected probe, not pure deionized water.
- Turbidity: Nephelometric Turbidity Units (NTU). Non-negative. Values > 1000 NTU indicate
  optical obstruction, severe sludge, or saturation, flagged for manual review.
- Temperature: Celsius. Hardware specification: DS18B20 supported range [-55.0, 125.0] °C.
  Values <= 0.5 °C, -127.0 °C (device disconnected), or 85.0 °C (power-on reset code)
  represent sensor dropouts or communication failures in atmospheric water tanks.
- Optical Colour Index (OCI): Derived relative index [0.0, 1.0]. Missing when unmeasured;
  never implicitly coerced to 0.0.
- Raw RGB: Red, Green, Blue raw counts / relative intensity (0-100). Display-only telemetry,
  never fed into 4-parameter water-quality ML models.
"""

from __future__ import annotations

from enum import Enum
import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional


class SensorQualityFlag(str, Enum):
    """Quality classification for a sensor parameter observation."""

    VALID = "VALID"                   # Physically plausible, normal measurement
    DROPOUT = "DROPOUT"               # Open-circuit, disconnected probe, or hardware reset code
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"   # Physically impossible or outside hardware limits
    SUSPECT_HIGH = "SUSPECT_HIGH"     # Unusually high for drinking tank, retained for review
    MISSING = "MISSING"               # Non-numeric, NaN, Infinity, None, or absent


@dataclass(frozen=True)
class ParameterValidationResult:
    """Detailed validation outcome for a single parameter measurement."""

    parameter: str
    raw_value: Any
    coerced_value: Optional[float]
    flag: SensorQualityFlag
    is_valid_for_model: bool
    is_valid_for_alerts: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize validation result to JSON-compatible dictionary."""
        return {
            "parameter": self.parameter,
            "raw_value": str(self.raw_value) if self.raw_value is not None else None,
            "coerced_value": self.coerced_value,
            "flag": self.flag.value,
            "is_valid_for_model": self.is_valid_for_model,
            "is_valid_for_alerts": self.is_valid_for_alerts,
            "reason": self.reason,
        }


def _coerce_numeric(val: Any) -> Optional[float]:
    """Coerce value to finite float or None if missing or invalid.

    Rejects None, booleans, non-numeric strings, NaN, and positive/negative infinity.
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(str(val).strip()) if isinstance(val, str) else float(val)
        if not math.isfinite(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def validate_parameter(param: str, raw_val: Any) -> ParameterValidationResult:
    """Validate a single water-quality parameter observation against physical and hardware rules.

    Args:
        param: Parameter name (e.g. 'pH', 'tds', 'turbidity', 'temperature', 'optical_colour_index').
        raw_val: Raw observation value from telemetry, database, or API request.

    Returns:
        ParameterValidationResult containing coerced value, quality flag, validity booleans, and explanation.
    """
    p = param.strip().lower()
    coerced = _coerce_numeric(raw_val)

    # 1. Missing or non-finite values
    if coerced is None:
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=None,
            flag=SensorQualityFlag.MISSING,
            is_valid_for_model=False,
            is_valid_for_alerts=False,
            reason=f"{param} value is missing, non-numeric, or non-finite ({raw_val!r}).",
        )

    # 2. pH validation
    if p == "ph":
        if coerced < 0.0 or coerced > 14.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.OUT_OF_BOUNDS,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"pH {coerced:.2f} is outside physical aqueous range [0.0, 14.0].",
            )
        if coerced <= 0.05:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.DROPOUT,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"pH {coerced:.2f} <= 0.05 indicates 0V ADC sensor dropout or disconnected probe.",
            )
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=coerced,
            flag=SensorQualityFlag.VALID,
            is_valid_for_model=True,
            is_valid_for_alerts=True,
            reason="pH is physically valid.",
        )

    # 3. TDS validation
    if p == "tds":
        if coerced < 0.0 or coerced > 10000.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.OUT_OF_BOUNDS,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"TDS {coerced:.2f} ppm is outside physical range [0.0, 10000.0] ppm.",
            )
        if coerced == 0.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.DROPOUT,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason="TDS 0.0 ppm indicates suspected sensor disconnect or unimmersed probe.",
            )
        if coerced > 2000.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.SUSPECT_HIGH,
                is_valid_for_model=True,
                is_valid_for_alerts=True,
                reason=f"TDS {coerced:.2f} ppm is unusually high for domestic water; retained for review.",
            )
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=coerced,
            flag=SensorQualityFlag.VALID,
            is_valid_for_model=True,
            is_valid_for_alerts=True,
            reason="TDS is physically valid.",
        )

    # 4. Turbidity validation
    if p == "turbidity":
        if coerced < 0.0 or coerced > 10000.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.OUT_OF_BOUNDS,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"Turbidity {coerced:.2f} NTU is outside physical optical bounds [0.0, 10000.0] NTU.",
            )
        if coerced > 1000.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.SUSPECT_HIGH,
                is_valid_for_model=True,
                is_valid_for_alerts=True,
                reason=f"Turbidity {coerced:.2f} NTU > 1000 indicates heavy sediment or sensor obstruction; retained for review.",
            )
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=coerced,
            flag=SensorQualityFlag.VALID,
            is_valid_for_model=True,
            is_valid_for_alerts=True,
            reason="Turbidity is physically valid.",
        )

    # 5. Temperature validation
    if p in ("temperature", "temp"):
        # Specific DS18B20 DallasTemperature hardware disconnect/reset constants
        if math.isclose(coerced, -127.0, abs_tol=0.5) or math.isclose(coerced, 85.0, abs_tol=0.5):
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.DROPOUT,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"Temperature {coerced:.2f} °C matches DS18B20 disconnect (-127°C) or power-on reset (85°C) error code.",
            )
        # Hardware limits for DS18B20: [-55, 125] °C
        if coerced < -55.0 or coerced > 125.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.OUT_OF_BOUNDS,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"Temperature {coerced:.2f} °C is outside DS18B20 hardware limits [-55.0, 125.0] °C.",
            )
        # In domestic water tanks in tropical climates, temperature <= 0.5 °C is an unimmersed probe/0V dropout.
        if coerced <= 0.5:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.DROPOUT,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"Temperature {coerced:.2f} °C <= 0.5 °C represents a sensor dropout or disconnected analog probe in water.",
            )
        if coerced > 60.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.SUSPECT_HIGH,
                is_valid_for_model=True,
                is_valid_for_alerts=True,
                reason=f"Temperature {coerced:.2f} °C > 60.0 °C is unusually high for storage tanks; retained for review.",
            )
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=coerced,
            flag=SensorQualityFlag.VALID,
            is_valid_for_model=True,
            is_valid_for_alerts=True,
            reason="Temperature is physically valid.",
        )

    # 6. Optical Colour Index (OCI) validation
    if p in ("optical_colour_index", "oci"):
        if coerced < 0.0 or coerced > 1.0:
            return ParameterValidationResult(
                parameter=param,
                raw_value=raw_val,
                coerced_value=coerced,
                flag=SensorQualityFlag.OUT_OF_BOUNDS,
                is_valid_for_model=False,
                is_valid_for_alerts=False,
                reason=f"Optical Colour Index {coerced:.4f} is outside normalized range [0.0, 1.0].",
            )
        return ParameterValidationResult(
            parameter=param,
            raw_value=raw_val,
            coerced_value=coerced,
            flag=SensorQualityFlag.VALID,
            is_valid_for_model=True,
            is_valid_for_alerts=True,
            reason="Optical Colour Index is valid.",
        )

    # Unknown parameter fallback
    return ParameterValidationResult(
        parameter=param,
        raw_value=raw_val,
        coerced_value=coerced,
        flag=SensorQualityFlag.VALID,
        is_valid_for_model=True,
        is_valid_for_alerts=True,
        reason=f"Unrecognized parameter {param}; treated as generic numeric.",
    )


def validate_reading_payload(payload: Mapping[str, Any]) -> dict[str, ParameterValidationResult]:
    """Validate all recognized water quality parameters in an observation payload."""
    results: dict[str, ParameterValidationResult] = {}
    for key, val in payload.items():
        if key.lower() in ("ph", "tds", "turbidity", "temperature", "temp", "optical_colour_index", "oci"):
            results[key.lower()] = validate_parameter(key, val)
    return results


def is_physically_valid_for_alerts(param: str, val: Any) -> bool:
    """Return True if value is valid to evaluate thresholds or resolve active alerts.

    Rejects dropouts (pH <= 0.05, TDS == 0.0, Temp <= 0.5), unphysical values, and missing data.
    """
    res = validate_parameter(param, val)
    return res.is_valid_for_alerts


def coerce_model_parameter(param: str, val: Any) -> Optional[float]:
    """Convert raw parameter value to clean float for model input, or None if dropout/invalid.

    Prevents corrupted sensor dropouts, unphysical values, and fabricated zeros from reaching ML models.
    """
    res = validate_parameter(param, val)
    return res.coerced_value if res.is_valid_for_model else None


def classify_observation(
    results: Mapping[str, ParameterValidationResult],
) -> tuple[str, Optional[str], bool]:
    """Classify an observation's overall quality and determine normalizability.

    An observation is normalizable (eligible for persistence in the normalized
    sensor_readings table) iff all three core required parameters (pH, TDS,
    and turbidity) are valid for model/storage under current validation rules.
    Temperature is optional in sensor_readings: if valid, it is included; if missing
    or dropout, it is omitted (NULL) without blocking normal persistence of pH, TDS,
    and turbidity.

    Returns:
        (overall_status, rejection_reason, is_normalizable)
        overall_status: "VALID", "PARTIALLY_VALID", "DROPOUT", "OUT_OF_BOUNDS", "MISSING", or "EMPTY"
        rejection_reason: Concisely explains any rejected or suspect parameters, or None if completely valid.
        is_normalizable: True iff the observation can be safely stored in sensor_readings.
    """
    if not results:
        return "EMPTY", "No parameter results provided in observation payload.", False

    # Standardize keys to lowercase
    norm_results = {k.strip().lower(): v for k, v in results.items()}

    # Required parameters for sensor_readings
    required_keys = ("ph", "tds", "turbidity")
    missing_required = [
        k for k in required_keys if k not in norm_results or norm_results[k].flag == SensorQualityFlag.MISSING
    ]
    dropouts = [v for v in norm_results.values() if v.flag == SensorQualityFlag.DROPOUT]
    out_of_bounds = [v for v in norm_results.values() if v.flag == SensorQualityFlag.OUT_OF_BOUNDS]
    suspect_highs = [v for v in norm_results.values() if v.flag == SensorQualityFlag.SUSPECT_HIGH]
    valids = [v for v in norm_results.values() if v.flag == SensorQualityFlag.VALID]

    # Check normalizability (ph, tds, turbidity must be valid for model/storage)
    is_normalizable = all(
        k in norm_results and norm_results[k].is_valid_for_model
        for k in required_keys
    )

    # Build concise reason
    reasons: list[str] = []
    for k, v in norm_results.items():
        if v.flag in (SensorQualityFlag.DROPOUT, SensorQualityFlag.OUT_OF_BOUNDS, SensorQualityFlag.MISSING):
            reasons.append(f"{v.parameter}: {v.flag.value} ({v.reason})")
        elif v.flag == SensorQualityFlag.SUSPECT_HIGH:
            reasons.append(f"{v.parameter}: {v.flag.value} (retained for review)")

    rejection_reason = "; ".join(reasons) if reasons else None

    # Determine overall status
    total_count = len(norm_results)
    if len(dropouts) == total_count:
        overall_status = "DROPOUT"
    elif len(out_of_bounds) == total_count:
        overall_status = "OUT_OF_BOUNDS"
    elif len(missing_required) == len(required_keys) and not valids:
        overall_status = "MISSING"
    elif not reasons or (len(valids) + len(suspect_highs) == total_count):
        overall_status = "VALID"
    else:
        overall_status = "PARTIALLY_VALID"

    return overall_status, rejection_reason, is_normalizable
