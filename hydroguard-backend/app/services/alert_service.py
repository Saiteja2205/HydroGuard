"""Service for alert generation and management.

Handles generating alerts based on parameter thresholds and managing alert lifecycle.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.repositories import AlertRepository, NodeRepository, SensorReadingRepository


class AlertService:
    """Service for alert generation and management operations."""

    # Default thresholds for alert generation
    DEFAULT_THRESHOLDS = {
        "ph": {"min": 6.5, "max": 8.5},
        "tds": {"max": 500.0},
        "turbidity": {"max": 5.0},
        "temperature": {"min": 15.0, "max": 30.0},
    }

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
            custom_thresholds: Optional custom thresholds (overrides defaults)

        Returns:
            List of generated alerts
        """
        thresholds = custom_thresholds or AlertService.DEFAULT_THRESHOLDS
        alerts = []

        # Evaluate pH
        if "ph" in reading_data:
            ph = reading_data["ph"]
            if "min" in thresholds["ph"] and ph < thresholds["ph"]["min"]:
                alerts.append(
                    AlertRepository.create(
                        db=db,
                        node_id=node_id,
                        timestamp=datetime.now(timezone.utc),
                        parameter="pH",
                        value=ph,
                        threshold=thresholds["ph"]["min"],
                        severity="WARNING",
                        message=f"pH below minimum threshold: {ph:.2f} < {thresholds['ph']['min']}",
                        status="ACTIVE",
                    )
                )
            elif "max" in thresholds["ph"] and ph > thresholds["ph"]["max"]:
                alerts.append(
                    AlertRepository.create(
                        db=db,
                        node_id=node_id,
                        timestamp=datetime.now(timezone.utc),
                        parameter="pH",
                        value=ph,
                        threshold=thresholds["ph"]["max"],
                        severity="WARNING",
                        message=f"pH above maximum threshold: {ph:.2f} > {thresholds['ph']['max']}",
                        status="ACTIVE",
                    )
                )

        # Evaluate TDS
        if "tds" in reading_data:
            tds = reading_data["tds"]
            if "max" in thresholds["tds"] and tds > thresholds["tds"]["max"]:
                alerts.append(
                    AlertRepository.create(
                        db=db,
                        node_id=node_id,
                        timestamp=datetime.now(timezone.utc),
                        parameter="TDS",
                        value=tds,
                        threshold=thresholds["tds"]["max"],
                        severity="WARNING",
                        message=f"TDS above maximum threshold: {tds:.2f} > {thresholds['tds']['max']}",
                        status="ACTIVE",
                    )
                )

        # Evaluate turbidity
        if "turbidity" in reading_data:
            turbidity = reading_data["turbidity"]
            if "max" in thresholds["turbidity"] and turbidity > thresholds["turbidity"]["max"]:
                alerts.append(
                    AlertRepository.create(
                        db=db,
                        node_id=node_id,
                        timestamp=datetime.now(timezone.utc),
                        parameter="turbidity",
                        value=turbidity,
                        threshold=thresholds["turbidity"]["max"],
                        severity="WARNING",
                        message=f"Turbidity above maximum threshold: {turbidity:.2f} > {thresholds['turbidity']['max']}",
                        status="ACTIVE",
                    )
                )

        # Evaluate temperature
        if "temperature" in reading_data:
            temp = reading_data["temperature"]
            if temp is not None:
                if "min" in thresholds["temperature"] and temp < thresholds["temperature"]["min"]:
                    alerts.append(
                        AlertRepository.create(
                            db=db,
                            node_id=node_id,
                            timestamp=datetime.now(timezone.utc),
                            parameter="temperature",
                            value=temp,
                            threshold=thresholds["temperature"]["min"],
                            severity="INFO",
                            message=f"Temperature below minimum threshold: {temp:.2f} < {thresholds['temperature']['min']}",
                            status="ACTIVE",
                        )
                    )
                elif "max" in thresholds["temperature"] and temp > thresholds["temperature"]["max"]:
                    alerts.append(
                        AlertRepository.create(
                            db=db,
                            node_id=node_id,
                            timestamp=datetime.now(timezone.utc),
                            parameter="temperature",
                            value=temp,
                            threshold=thresholds["temperature"]["max"],
                            severity="INFO",
                            message=f"Temperature above maximum threshold: {temp:.2f} > {thresholds['temperature']['max']}",
                            status="ACTIVE",
                        )
                    )

        return alerts

    @staticmethod
    def get_active_alerts(db: Session, node_id: str) -> list:
        """Get all active alerts for a node.

        Args:
            db: Database session
            node_id: Node identifier

        Returns:
            List of active alerts
        """
        return AlertRepository.get_active_by_node(db, node_id)

    @staticmethod
    def acknowledge_alert(db: Session, alert_id: int) -> Optional:
        """Acknowledge an alert.

        Args:
            db: Database session
            alert_id: Alert ID

        Returns:
            Updated alert or None
        """
        return AlertRepository.update_status(db, alert_id, "ACKNOWLEDGED")

    @staticmethod
    def resolve_alert(db: Session, alert_id: int) -> Optional:
        """Resolve an alert.

        Args:
            db: Database session
            alert_id: Alert ID

        Returns:
            Updated alert or None
        """
        return AlertRepository.update_status(db, alert_id, "RESOLVED")
