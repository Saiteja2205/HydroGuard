"""Tests for FCM push notification service, device registration, and alert dispatch."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.db.database import get_db_context, init_db
from app.db.models import Alert, AlertNotificationLog, DeviceToken
from app.db.repositories import (
    AlertNotificationRepository,
    AlertRepository,
    DeviceTokenRepository,
    NodeRepository,
)
from app.main import app
from app.services.push_notification_service import PushNotificationService


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    with get_db_context() as db:
        db.query(AlertNotificationLog).delete()
        db.query(DeviceToken).delete()
        db.commit()


def test_device_token_repository():
    """Verify registration, query, deactivation, and pruning in DeviceTokenRepository."""
    with get_db_context() as db:
        # Register a token for an admin
        token1 = DeviceTokenRepository.register_token(
            db=db,
            user_uid="admin_user_1",
            role="admin",
            token="fcm_token_admin_abc123",
            device_type="android",
        )
        assert token1.user_uid == "admin_user_1"
        assert token1.role == "admin"
        assert token1.is_active is True

        # Register a token for a student
        token2 = DeviceTokenRepository.register_token(
            db=db,
            user_uid="student_user_1",
            role="student",
            token="fcm_token_student_xyz789",
            device_type="android",
        )
        assert token2.user_uid == "student_user_1"
        assert token2.role == "student"

        # Updating existing token preserves uniqueness and updates fields
        token1_updated = DeviceTokenRepository.register_token(
            db=db,
            user_uid="admin_user_1",
            role="admin",
            token="fcm_token_admin_abc123",
            device_type="android_tablet",
        )
        assert token1_updated.device_type == "android_tablet"

        # Query active tokens by role
        admin_tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, ["admin"])
        assert "fcm_token_admin_abc123" in admin_tokens
        assert "fcm_token_student_xyz789" not in admin_tokens

        student_tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, ["student"])
        assert "fcm_token_student_xyz789" in student_tokens

        # Cleanup invalid tokens
        deactivated = DeviceTokenRepository.cleanup_invalid_tokens(db, ["fcm_token_admin_abc123"])
        assert deactivated == 1
        admin_tokens_after = DeviceTokenRepository.get_active_tokens_for_roles(db, ["admin"])
        assert "fcm_token_admin_abc123" not in admin_tokens_after

        # Deactivate student token on logout
        deactivated_user = DeviceTokenRepository.deactivate_user_tokens(db, "student_user_1")
        assert deactivated_user == 1
        student_tokens_after = DeviceTokenRepository.get_active_tokens_for_roles(db, ["student"])
        assert "fcm_token_student_xyz789" not in student_tokens_after


def test_device_api_endpoints(monkeypatch):
    """Test POST /api/v1/devices/register and /api/v1/devices/unregister."""
    client = TestClient(app)

    # 1. Register with student authentication
    monkeypatch.setitem(
        app.dependency_overrides,
        authenticated_principal,
        lambda: {"uid": "auth_student_99", "role": "student"},
    )
    resp = client.post(
        "/api/v1/devices/register",
        json={"token": "valid_fcm_test_token_1234567890", "device_type": "android"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"
    assert data["user_uid"] == "auth_student_99"
    assert data["role"] == "student"

    # Verify registered in DB
    with get_db_context() as db:
        tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, ["student"])
        assert "valid_fcm_test_token_1234567890" in tokens

    # 2. Unregister token
    resp_unreg = client.post(
        "/api/v1/devices/unregister",
        json={"token": "valid_fcm_test_token_1234567890"},
    )
    assert resp_unreg.status_code == 200
    assert resp_unreg.json()["status"] == "unregistered"
    assert resp_unreg.json()["deactivated"] is True

    # Verify deactivated in DB
    with get_db_context() as db:
        tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, ["student"])
        assert "valid_fcm_test_token_1234567890" not in tokens


def test_push_notification_service_formatting_and_idempotency(monkeypatch):
    """Verify role-based notification formatting, deduplication, and multicast dispatch."""
    with get_db_context() as db:
        NodeRepository.get_or_create(db, "thingspeak-244357", "Hostel Tank", "Roof")
        alert = AlertRepository.create(
            db=db,
            node_id="thingspeak-244357",
            timestamp=datetime.now(timezone.utc),
            parameter="pH",
            value=12.41,
            threshold=8.5,
            severity="CRITICAL",
            message="pH level 12.41 exceeds maximum threshold 8.5",
        )

        # Register active tokens for both admin and student
        DeviceTokenRepository.register_token(
            db=db,
            user_uid="admin_test",
            role="admin",
            token="admin_fcm_token_valid_111",
        )
        DeviceTokenRepository.register_token(
            db=db,
            user_uid="student_test",
            role="student",
            token="student_fcm_token_valid_222",
        )

        # Mock Firebase app and send_each_for_multicast
        mock_app = MagicMock()
        mock_response = MagicMock()
        mock_response.success_count = 1
        mock_response.failure_count = 0
        mock_response.responses = [MagicMock(success=True, exception=None)]

        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_response) as mock_send:
            # First notification dispatch
            results = PushNotificationService.notify_alert_created(db, alert, app=mock_app)
            assert results["admin"]["status"] == "SENT"
            assert results["student"]["status"] == "SENT"
            assert mock_send.call_count == 2  # Once for admin, once for student

            # Verify logs stored in outbox table
            admin_notified = AlertNotificationRepository.is_alert_notified(db, alert.id, "admin")
            student_notified = AlertNotificationRepository.is_alert_notified(db, alert.id, "student")
            assert admin_notified is True
            assert student_notified is True

            # Second notification attempt on the SAME alert must be skipped (idempotency)
            results_dup = PushNotificationService.notify_alert_created(db, alert, app=mock_app)
            assert results_dup["admin"]["status"] == "SKIPPED_DUPLICATE"
            assert results_dup["student"]["status"] == "SKIPPED_DUPLICATE"
            # Send count should not have increased
            assert mock_send.call_count == 2


def test_push_notification_service_invalid_token_pruning(monkeypatch):
    """Verify that tokens returning UnregisteredError are automatically marked inactive."""
    with get_db_context() as db:
        NodeRepository.get_or_create(db, "node_push_test_a", "Test Push Tank A", "Roof")
        alert = AlertRepository.create(
            db=db,
            node_id="node_push_test_a",
            timestamp=datetime.now(timezone.utc),
            parameter="turbidity",
            value=25.0,
            threshold=5.0,
            severity="WARNING",
            message="Turbidity elevated",
        )

        invalid_token = "invalid_expired_token_9999"
        DeviceTokenRepository.register_token(
            db=db,
            user_uid="student_with_old_device",
            role="student",
            token=invalid_token,
        )

        mock_app = MagicMock()
        mock_response = MagicMock()
        mock_response.success_count = 0
        mock_response.failure_count = 1

        from firebase_admin import messaging
        mock_send_response = MagicMock(
            success=False,
            exception=messaging.UnregisteredError("Requested entity was not found: registration-token-not-registered"),
        )
        mock_response.responses = [mock_send_response]

        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_response):
            results = PushNotificationService.notify_alert_created(db, alert, app=mock_app)
            assert results["student"]["failure_count"] == 1

        # Token should now be deactivated in the database
        active_student_tokens = DeviceTokenRepository.get_active_tokens_for_roles(db, ["student"])
        assert invalid_token not in active_student_tokens


def test_push_notification_service_skipped_when_unconfigured():
    """Verify that when Firebase is unconfigured, alert creation is logged without raising errors."""
    with get_db_context() as db:
        NodeRepository.get_or_create(db, "node_push_test_b", "Test Push Tank B", "Roof")
        alert = AlertRepository.create(
            db=db,
            node_id="node_push_test_b",
            timestamp=datetime.now(timezone.utc),
            parameter="TDS",
            value=650.0,
            threshold=500.0,
            severity="WARNING",
            message="TDS elevated",
        )

        DeviceTokenRepository.register_token(
            db=db,
            user_uid="admin_unconfigured",
            role="admin",
            token="fcm_token_admin_unconfigured_123",
        )

        with patch.object(PushNotificationService, "get_firebase_app_safely", return_value=None):
            results = PushNotificationService.notify_alert_created(db, alert)
            assert results["admin"]["status"] == "SKIPPED_NOT_CONFIGURED"

            # Check log record
            logs = AlertNotificationRepository.get_logs_for_alert(db, alert.id)
            admin_log = next(log for log in logs if log.recipient_role == "admin")
            assert admin_log.status == "SKIPPED_NOT_CONFIGURED"
