"""Service for alert generation and management.

Handles generating alerts based on parameter thresholds and managing alert lifecycle.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.repositories import AlertRepository, NodeRepository, SensorReadingRepository, ThresholdRepository


def _coerce_numeric(val: Any) -> Optional[float]:
    """Coerce value to finite float or None if invalid/missing.

    Rejects None, booleans, strings that cannot be parsed as floats, NaN, and infinities.
    """
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        if not math.isfinite(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def is_physically_valid(param: str, val: Any) -> bool:
    """Validate that a sensor observation represents a physically plausible aqueous reading.

    Rejects:
    - Non-numeric, non-finite values (NaN, infinity, None, booleans)
    - Open-circuit / 0V ADC sensor dropouts (e.g. pH <= 0.05, temperature <= 0.5)
    - Unphysical or out-of-range sensor values (e.g. pH < 0.5 or > 14.0, negative TDS, negative turbidity)
    """
    f = _coerce_numeric(val)
    if f is None:
        return False
    p = param.strip().lower()
    if p in ("ph",):
        # Aqueous water: 0.5 <= pH <= 14.0. Values <= 0.05 are open-circuit 0V probe dropouts.
        return 0.5 <= f <= 14.0
    elif p in ("tds",):
        # TDS in ppm: non-negative, plausible range up to 5000 ppm
        return 0.0 <= f <= 5000.0
    elif p in ("turbidity",):
        # Turbidity in NTU: non-negative, plausible range up to 3000 NTU
        return 0.0 <= f <= 3000.0
    elif p in ("temperature", "temp"):
        # Water temperature in Celsius: 0.5 <= temp <= 75.0 (0.0 or <= 0.5 is probe disconnect/dropout)
        return 0.5 <= f <= 75.0
    elif p in ("optical_colour_index", "oci"):
        return 0.0 <= f <= 10.0
    return True


class AlertService:
    """Service for alert generation and management operations."""

    # Default thresholds for alert generation; overridden by threshold_configs rows.
    DEFAULT_THRESHOLDS = {
        "ph": {"min": 6.5, "max": 8.5},
        "tds": {"max": 500.0},
        "turbidity": {"max": 5.0},
        "temperature": {"min": 15.0, "max": 30.0},
        "optical_colour_index": {"max": 1.0},
    }

    # Default cooldown period in minutes to prevent alert spam
    DEFAULT_COOLDOWN_MINUTES = 60

    @staticmethod
    def get_effective_thresholds(db: Session) -> dict:
        """Merge stored admin-configured thresholds over the built-in defaults."""
        thresholds = {
            parameter: dict(bounds) for parameter, bounds in AlertService.DEFAULT_THRESHOLDS.items()
        }
        for row in ThresholdRepository.get_all(db):
            key = row.parameter.strip().lower()
            bounds: dict = {}
            if row.min_value is not None:
                bounds["min"] = float(row.min_value)
            if row.max_value is not None:
                bounds["max"] = float(row.max_value)
            if bounds:
                thresholds[key] = bounds
        return thresholds

    @staticmethod
    def get_cooldown_minutes(db: Session) -> int:
        """Get configured cooldown period, defaulting to DEFAULT_COOLDOWN_MINUTES."""
        # Could be extended to read from a settings table
        return AlertService.DEFAULT_COOLDOWN_MINUTES

    @staticmethod
    def evaluate_reading_for_alerts(
        db: Session,
        node_id: str,
        reading_data: dict,
        custom_thresholds: Optional[dict] = None,
    ) -> list:
        """Evaluate a reading against thresholds and generate alerts if needed.

        Args:
            db: Database session
            node_id: Node identifier
            reading_data: Dictionary of parameter values
            custom_thresholds: Optional custom thresholds (overrides stored defaults)

        Returns:
            List of generated alerts
        """
        thresholds = custom_thresholds or AlertService.get_effective_thresholds(db)
        cooldown_minutes = AlertService.get_cooldown_minutes(db)
        alert_timestamp = reading_data.get("timestamp")
        if not isinstance(alert_timestamp, datetime):
            alert_timestamp = datetime.now(timezone.utc)
        alerts = []

        # Evaluate pH
        if "ph" in reading_data:
            ph = _coerce_numeric(reading_data.get("ph"))
            if ph is not None and is_physically_valid("ph", ph) and "ph" in thresholds:
                if "min" in thresholds["ph"] and ph < thresholds["ph"]["min"]:
                    alerts.append(AlertService._maybe_create_alert(
                        db=db,
                        node_id=node_id,
                        timestamp=alert_timestamp,
                        parameter="pH",
                        value=ph,
                        threshold=thresholds["ph"]["min"],
                        severity="WARNING",
                        message=f"pH below minimum threshold: {ph:.2f} < {thresholds['ph']['min']}",
                        cooldown_minutes=cooldown_minutes,
                    ))
                elif "max" in thresholds["ph"] and ph > thresholds["ph"]["max"]:
                    alerts.append(AlertService._maybe_create_alert(
                        db=db,
                        node_id=node_id,
                        timestamp=alert_timestamp,
                        parameter="pH",
                        value=ph,
                        threshold=thresholds["ph"]["max"],
                        severity="WARNING",
                        message=f"pH above maximum threshold: {ph:.2f} > {thresholds['ph']['max']}",
                        cooldown_minutes=cooldown_minutes,
                    ))

        # Evaluate TDS
        if "tds" in reading_data:
            tds = _coerce_numeric(reading_data.get("tds"))
            if tds is not None and is_physically_valid("tds", tds) and "tds" in thresholds and "max" in thresholds["tds"] and tds > thresholds["tds"]["max"]:
                alerts.append(AlertService._maybe_create_alert(
                    db=db,
                    node_id=node_id,
                    timestamp=alert_timestamp,
                    parameter="TDS",
                    value=tds,
                    threshold=thresholds["tds"]["max"],
                    severity="WARNING",
                    message=f"TDS above maximum threshold: {tds:.2f} > {thresholds['tds']['max']}",
                    cooldown_minutes=cooldown_minutes,
                ))

        # Evaluate turbidity
        if "turbidity" in reading_data:
            turbidity = _coerce_numeric(reading_data.get("turbidity"))
            if turbidity is not None and is_physically_valid("turbidity", turbidity) and "turbidity" in thresholds and "max" in thresholds["turbidity"] and turbidity > thresholds["turbidity"]["max"]:
                alerts.append(AlertService._maybe_create_alert(
                    db=db,
                    node_id=node_id,
                    timestamp=alert_timestamp,
                    parameter="turbidity",
                    value=turbidity,
                    threshold=thresholds["turbidity"]["max"],
                    severity="WARNING",
                    message=f"Turbidity above maximum threshold: {turbidity:.2f} > {thresholds['turbidity']['max']}",
                    cooldown_minutes=cooldown_minutes,
                ))

        # Evaluate temperature
        if "temperature" in reading_data:
            temp = _coerce_numeric(reading_data.get("temperature"))
            if temp is not None and is_physically_valid("temperature", temp) and "temperature" in thresholds:
                if "min" in thresholds["temperature"] and temp < thresholds["temperature"]["min"]:
                    alerts.append(AlertService._maybe_create_alert(
                        db=db,
                        node_id=node_id,
                        timestamp=alert_timestamp,
                        parameter="temperature",
                        value=temp,
                        threshold=thresholds["temperature"]["min"],
                        severity="INFO",
                        message=f"Temperature below minimum threshold: {temp:.2f} < {thresholds['temperature']['min']}",
                        cooldown_minutes=cooldown_minutes,
                    ))
                elif "max" in thresholds["temperature"] and temp > thresholds["temperature"]["max"]:
                    alerts.append(AlertService._maybe_create_alert(
                        db=db,
                        node_id=node_id,
                        timestamp=alert_timestamp,
                        parameter="temperature",
                        value=temp,
                        threshold=thresholds["temperature"]["max"],
                        severity="INFO",
                        message=f"Temperature above maximum threshold: {temp:.2f} > {thresholds['temperature']['max']}",
                        cooldown_minutes=cooldown_minutes,
                    ))

        # Evaluate optical colour index
        if "optical_colour_index" in reading_data:
            oci = _coerce_numeric(reading_data.get("optical_colour_index"))
            if oci is not None and is_physically_valid("optical_colour_index", oci) and "max" in thresholds.get("optical_colour_index", {}) and oci > thresholds["optical_colour_index"]["max"]:
                alerts.append(AlertService._maybe_create_alert(
                    db=db,
                    node_id=node_id,
                    timestamp=alert_timestamp,
                    parameter="optical_colour_index",
                    value=oci,
                    threshold=thresholds["optical_colour_index"]["max"],
                    severity="INFO",
                    message=f"Optical colour index above maximum threshold: {oci:.4f} > {thresholds['optical_colour_index']['max']}",
                    cooldown_minutes=cooldown_minutes,
                ))

        return [a for a in alerts if a is not None]

    @staticmethod
    def _maybe_create_alert(
        db: Session,
        node_id: str,
        timestamp: datetime,
        parameter: str,
        value: float,
        threshold: float,
        severity: str,
        message: str,
        cooldown_minutes: int,
    ):
        """Create alert only if no duplicate or recent similar alert exists."""
        # 1. Prevent duplicate alert creation on repeated polling of the exact same reading
        if AlertRepository.exists_for_reading(db, node_id, parameter, timestamp):
            return None

        # 2. Prevent creating duplicate active alerts when one is already open for this parameter
        if AlertRepository.get_open_alert(db, node_id, parameter) is not None:
            return None

        # 3. Check cooldown period
        if cooldown_minutes > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
            recent = AlertRepository.get_recent_similar(db, node_id, parameter, threshold, cutoff)
            if recent:
                return None  # Skip: similar alert recently created

        return AlertRepository.create(
            db=db,
            node_id=node_id,
            timestamp=timestamp,
            parameter=parameter,
            value=value,
            threshold=threshold,
            severity=severity,
            message=message,
            status="ACTIVE",
        )

    @staticmethod
    def check_and_resolve_alerts(
        db: Session,
        node_id: str,
        reading_data: dict,
        custom_thresholds: Optional[dict] = None,
    ) -> int:
        """Check existing active alerts and resolve those that are no longer violated.

        Guards against:
        - Invalid readings / sensor dropouts (e.g. 0V dropouts): cannot resolve alerts.
        - Missing parameters: cannot resolve alerts.
        - Stale readings: reading timestamp older than the alert timestamp cannot resolve alerts.
        - Simulated readings: cannot resolve real ThingSpeak alerts.

        Args:
            db: Database session
            node_id: Node identifier
            reading_data: Current reading data
            custom_thresholds: Optional custom thresholds

        Returns:
            Number of alerts resolved
        """
        # Guard against simulated readings resolving real ThingSpeak alerts
        if node_id.startswith("thingspeak-") and str(reading_data.get("source", "")).strip().upper() in (
            "SIMULATED_DEVELOPMENT", "SIMULATED", "MOCK"
        ):
            return 0

        # Parse reading timestamp for staleness checking
        reading_ts = reading_data.get("timestamp")
        if isinstance(reading_ts, str):
            try:
                reading_ts = datetime.fromisoformat(reading_ts.replace("Z", "+00:00"))
            except Exception:
                reading_ts = None
        if isinstance(reading_ts, datetime) and reading_ts.tzinfo is None:
            reading_ts = reading_ts.replace(tzinfo=timezone.utc)

        thresholds = custom_thresholds or AlertService.get_effective_thresholds(db)
        active_alerts = AlertRepository.get_active_by_node(db, node_id)
        resolved_count = 0

        for alert in active_alerts:
            param = alert.parameter.lower()
            current_value = _coerce_numeric(reading_data.get(param))
            if current_value is None:
                continue

            # 1. Invalid / physical sensor dropout check
            if not is_physically_valid(param, current_value):
                continue

            # 2. Staleness check: a reading older than the alert cannot resolve it
            if reading_ts is not None and alert.timestamp is not None:
                alert_ts = alert.timestamp
                if alert_ts.tzinfo is None:
                    alert_ts = alert_ts.replace(tzinfo=timezone.utc)
                if reading_ts < alert_ts:
                    continue

            alert_threshold = _coerce_numeric(alert.threshold)
            if alert_threshold is None:
                continue

            should_resolve = False

            if param == "ph":
                min_thresh = thresholds.get("ph", {}).get("min")
                max_thresh = thresholds.get("ph", {}).get("max")
                if min_thresh is not None and math.isclose(alert_threshold, min_thresh, rel_tol=1e-4):
                    if current_value >= min_thresh and (max_thresh is None or current_value <= max_thresh):
                        should_resolve = True
                elif max_thresh is not None and math.isclose(alert_threshold, max_thresh, rel_tol=1e-4):
                    if current_value <= max_thresh and (min_thresh is None or current_value >= min_thresh):
                        should_resolve = True
            elif param == "tds" and "max" in thresholds.get("tds", {}):
                if current_value <= thresholds["tds"]["max"]:
                    should_resolve = True
            elif param == "turbidity" and "max" in thresholds.get("turbidity", {}):
                if current_value <= thresholds["turbidity"]["max"]:
                    should_resolve = True
            elif param == "temperature":
                min_thresh = thresholds.get("temperature", {}).get("min")
                max_thresh = thresholds.get("temperature", {}).get("max")
                if min_thresh is not None and math.isclose(alert_threshold, min_thresh, rel_tol=1e-4):
                    if current_value >= min_thresh and (max_thresh is None or current_value <= max_thresh):
                        should_resolve = True
                elif max_thresh is not None and math.isclose(alert_threshold, max_thresh, rel_tol=1e-4):
                    if current_value <= max_thresh and (min_thresh is None or current_value >= min_thresh):
                        should_resolve = True
            elif param == "optical_colour_index" and "max" in thresholds.get("optical_colour_index", {}):
                if current_value <= thresholds["optical_colour_index"]["max"]:
                    should_resolve = True

            if should_resolve:
                AlertRepository.update_status(db, alert.id, "RESOLVED")
                resolved_count += 1

        return resolved_count

    @staticmethod
    def get_active_alerts(db: Session, node_id: str) -> list:
        """Get all active alerts for a node."""
        return AlertRepository.get_active_by_node(db, node_id)

    @staticmethod
    def acknowledge_alert(db: Session, alert_id: int) -> Optional:
        """Acknowledge an alert."""
        return AlertRepository.update_status(db, alert_id, "ACKNOWLEDGED")

    @staticmethod
    def resolve_alert(db: Session, alert_id: int) -> Optional:
        """Resolve an alert."""
        return AlertRepository.update_status(db, alert_id, "RESOLVED")