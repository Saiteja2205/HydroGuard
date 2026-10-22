"""Push notification dispatch service for HydroGuard AI.

Handles formatting, role-based routing, multicast dispatch via Firebase Cloud
Messaging (FCM), invalid token pruning, and durable dispatch logging/deduplication.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.db.models import Alert
from app.db.repositories import AlertNotificationRepository, DeviceTokenRepository

logger = logging.getLogger(__name__)

# Max tokens per FCM multicast request according to Firebase API specs
MAX_MULTICAST_BATCH_SIZE = 500


class PushNotificationService:
    """Service for dispatching push notifications via Firebase Cloud Messaging."""

    @staticmethod
    def get_firebase_app_safely() -> Any:
        """Safely retrieve or initialize the Firebase app without raising 503."""
        try:
            from app.core.auth import _firebase_app

            return _firebase_app()
        except Exception as exc:
            logger.warning("Firebase app is not configured or unavailable: %s", exc)
            return None

    @staticmethod
    def format_admin_notification(alert: Alert) -> tuple[str, str]:
        """Format an operational alert notification for administrators."""
        node_label = alert.node_id
        if node_label.startswith("thingspeak-"):
            channel = node_label.replace("thingspeak-", "")
            node_label = f"Hostel Tank (ThingSpeak #{channel})"
        elif node_label == "node_overhead_a":
            node_label = "Hostel Water Tank A"
        elif node_label == "node_overhead_b":
            node_label = "Hostel Water Tank B"

        title = f"HydroGuard Alert: {alert.parameter} Breach"
        body = (
            f"Alert on {node_label}: {alert.parameter} is {alert.value:.2f} "
            f"(threshold: {alert.threshold:.2f}). Severity: {alert.severity}."
        )
        return title, body

    @staticmethod
    def format_student_notification(alert: Alert) -> tuple[str, str]:
        """Format a clear, non-technical water quality advisory for students."""
        param_upper = alert.parameter.upper()
        if "PH" in param_upper:
            title = "HydroGuard: Water Quality Advisory"
            if alert.value < 6.5:
                body = f"Water pH is acidic ({alert.value:.2f}). Safe range is 6.5–8.5."
            else:
                body = f"Water pH is alkaline ({alert.value:.2f}). Safe range is 6.5–8.5."
        elif "TURB" in param_upper:
            title = "HydroGuard: Water Clarity Advisory"
            body = f"Water turbidity is elevated ({alert.value:.1f} NTU). Water may appear cloudy."
        elif "TDS" in param_upper:
            title = "HydroGuard: High Mineral Advisory"
            body = f"Total Dissolved Solids (TDS) is high ({alert.value:.0f} ppm)."
        elif "TEMP" in param_upper:
            title = "HydroGuard: Water Temperature Advisory"
            body = f"Water temperature is abnormal ({alert.value:.1f} °C)."
        else:
            title = "HydroGuard: Water Advisory"
            body = f"Notice: {alert.parameter} reading is abnormal ({alert.value:.2f})."

        return title, body

    @classmethod
    def notify_alert_created(
        cls,
        db: Session,
        alert: Alert,
        app: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Evaluate and dispatch push notifications for a newly created alert.

        Ensures:
        1. Role-based routing (Admin operational alerts, Student advisories).
        2. Idempotency (deduplication check against alert_notification_logs).
        3. Multicast batching with invalid token pruning.
        4. Graceful fallback when Firebase is not configured.
        """
        if not alert or not alert.id:
            logger.warning("notify_alert_created called with invalid alert.")
            return {"status": "SKIPPED_INVALID_ALERT"}

        # Only notify active alerts
        if alert.status != "ACTIVE":
            logger.debug("Alert %s is not active; skipping push notification.", alert.id)
            return {"status": "SKIPPED_INACTIVE"}

        # Determine target recipient groups
        target_roles = ["admin"]
        # For water-quality alerts in hostel tanks, notify students as well
        target_roles.append("student")

        results: dict[str, Any] = {}

        for role in target_roles:
            # 1. Deduplication check
            if AlertNotificationRepository.is_alert_notified(db, alert.id, recipient_role=role):
                logger.debug(
                    "Alert %s has already been notified to role '%s'; skipping.",
                    alert.id,
                    role,
                )
                results[role] = {"status": "SKIPPED_DUPLICATE"}
                continue

            # 2. Query active tokens for this role
            tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, [role])
            if not tokens:
                AlertNotificationRepository.record_log(
                    db=db,
                    alert_id=alert.id,
                    recipient_role=role,
                    token_count=0,
                    success_count=0,
                    failure_count=0,
                    status="SKIPPED_NO_TOKENS",
                    error_detail=f"No active tokens registered for role '{role}'.",
                )
                results[role] = {"status": "SKIPPED_NO_TOKENS", "token_count": 0}
                continue

            # 3. Resolve Firebase App
            firebase_app = app if app is not None else cls.get_firebase_app_safely()
            if firebase_app is None:
                AlertNotificationRepository.record_log(
                    db=db,
                    alert_id=alert.id,
                    recipient_role=role,
                    token_count=len(tokens),
                    success_count=0,
                    failure_count=0,
                    status="SKIPPED_NOT_CONFIGURED",
                    error_detail="Firebase app credentials are not configured.",
                )
                logger.info(
                    "Firebase app not configured; push notification for alert %d (%s) skipped.",
                    alert.id,
                    role,
                )
                results[role] = {"status": "SKIPPED_NOT_CONFIGURED", "token_count": len(tokens)}
                continue

            # 4. Format message for this role
            if role == "admin":
                title, body = cls.format_admin_notification(alert)
            else:
                title, body = cls.format_student_notification(alert)

            data_payload = {
                "alert_id": str(alert.id),
                "node_id": str(alert.node_id),
                "parameter": str(alert.parameter),
                "severity": str(alert.severity),
                "value": f"{alert.value:.2f}",
                "threshold": f"{alert.threshold:.2f}",
                "target_screen": "water",
            }

            # 5. Dispatch multicast in batches
            dispatch_result = cls._dispatch_multicast(
                db=db,
                app=firebase_app,
                tokens=tokens,
                title=title,
                body=body,
                data=data_payload,
            )

            # 6. Record log
            status_str = "SENT" if dispatch_result["success_count"] > 0 else "FAILED"
            if dispatch_result["token_count"] == 0:
                status_str = "SKIPPED_NO_TOKENS"

            AlertNotificationRepository.record_log(
                db=db,
                alert_id=alert.id,
                recipient_role=role,
                token_count=dispatch_result["token_count"],
                success_count=dispatch_result["success_count"],
                failure_count=dispatch_result["failure_count"],
                status=status_str,
                error_detail=dispatch_result.get("error_detail"),
            )

            results[role] = {
                "status": status_str,
                "token_count": dispatch_result["token_count"],
                "success_count": dispatch_result["success_count"],
                "failure_count": dispatch_result["failure_count"],
            }

        return results

    @classmethod
    def _dispatch_multicast(
        cls,
        db: Session,
        app: Any,
        tokens: Sequence[str],
        title: str,
        body: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        """Dispatch multicast message to a list of tokens in batches."""
        try:
            from firebase_admin import messaging
        except ImportError as exc:
            logger.error("firebase_admin.messaging could not be imported: %s", exc)
            return {
                "token_count": len(tokens),
                "success_count": 0,
                "failure_count": len(tokens),
                "error_detail": f"ImportError: {exc}",
            }

        total_success = 0
        total_failure = 0
        invalid_tokens: list[str] = []
        last_error: Optional[str] = None

        # Split into batches of at most MAX_MULTICAST_BATCH_SIZE (500)
        for i in range(0, len(tokens), MAX_MULTICAST_BATCH_SIZE):
            batch_tokens = list(tokens[i : i + MAX_MULTICAST_BATCH_SIZE])
            try:
                message = messaging.MulticastMessage(
                    tokens=batch_tokens,
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data,
                    android=messaging.AndroidConfig(
                        priority="high",
                        notification=messaging.AndroidNotification(
                            channel_id="hydroguard_alerts",
                            sound="default",
                            priority="high",
                        ),
                    ),
                )

                response = messaging.send_each_for_multicast(message, app=app)
                total_success += response.success_count
                total_failure += response.failure_count

                # Prune invalid / unregistered tokens
                for idx, resp in enumerate(response.responses):
                    if not resp.success and resp.exception:
                        exc_name = type(resp.exception).__name__
                        exc_str = str(resp.exception).lower()
                        if (
                            isinstance(resp.exception, messaging.UnregisteredError)
                            or "unregistered" in exc_str
                            or "registration-token-not-registered" in exc_str
                            or "invalid-argument" in exc_str
                            or "invalid fcm registration token" in exc_str
                            or "invalidargumenterror" in exc_name.lower()
                        ):
                            invalid_tokens.append(batch_tokens[idx])
                        last_error = f"{exc_name}: {resp.exception}"

            except Exception as batch_exc:
                logger.error("Multicast batch dispatch failed: %s", batch_exc)
                total_failure += len(batch_tokens)
                last_error = str(batch_exc)

        # Deactivate any invalid tokens found
        if invalid_tokens:
            deactivated = DeviceTokenRepository.cleanup_invalid_tokens(db, invalid_tokens)
            logger.info("Deactivated %d invalid FCM tokens.", deactivated)

        return {
            "token_count": len(tokens),
            "success_count": total_success,
            "failure_count": total_failure,
            "error_detail": last_error,
        }
