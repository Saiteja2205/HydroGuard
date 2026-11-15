"""Tests for scripts.bootstrap_first_admin CLI tool."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from firebase_admin import auth as firebase_auth

from scripts import bootstrap_first_admin


def test_cli_missing_project_id(capsys, monkeypatch):
    monkeypatch.delenv("HYDROGUARD_FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "admin@college.edu"])

    code = bootstrap_first_admin.main()

    assert code == 2
    captured = capsys.readouterr()
    assert "HYDROGUARD_FIREBASE_PROJECT_ID is not set." in captured.err


def test_cli_project_id_mismatch(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "expected-project")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "admin@college.edu"])

    mock_app = SimpleNamespace(project_id="wrong-project")
    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: None)

    code = bootstrap_first_admin.main()

    assert code == 1
    captured = capsys.readouterr()
    assert "Firebase Admin initialized for a different project." in captured.err


def test_cli_user_not_found(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "unknown@college.edu"])

    mock_app = SimpleNamespace(project_id="hydroguard-4a606")
    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: None)

    def raise_not_found(email, app):
        raise firebase_auth.UserNotFoundError("User not found")

    monkeypatch.setattr(bootstrap_first_admin.firebase_auth, "get_user_by_email", raise_not_found)

    code = bootstrap_first_admin.main()

    assert code == 1
    captured = capsys.readouterr()
    assert "Firebase user not found. Have the account sign in once, then retry." in captured.err


def test_cli_runtime_error_reporting_preserves_error_message(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "admin@college.edu"])

    mock_app = SimpleNamespace(project_id="hydroguard-4a606")
    mock_fb_user = SimpleNamespace(uid="uid-1", email="admin@college.edu", email_verified=True)
    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: None)
    monkeypatch.setattr(bootstrap_first_admin.firebase_auth, "get_user_by_email", lambda email, app: mock_fb_user)
    monkeypatch.setattr(bootstrap_first_admin, "init_db", lambda: None)

    def raise_runtime(db, user):
        raise RuntimeError("An active HydroGuard administrator already exists.")

    monkeypatch.setattr(bootstrap_first_admin, "bootstrap_first_admin", raise_runtime)

    code = bootstrap_first_admin.main()

    assert code == 1
    captured = capsys.readouterr()
    assert "First administrator provisioning failed: An active HydroGuard administrator already exists." in captured.err


def test_cli_http_exception_reporting(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "admin@college.edu"])

    mock_app = SimpleNamespace(project_id="hydroguard-4a606")
    mock_fb_user = SimpleNamespace(uid="uid-1", email="admin@college.edu", email_verified=True)
    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: None)
    monkeypatch.setattr(bootstrap_first_admin.firebase_auth, "get_user_by_email", lambda email, app: mock_fb_user)
    monkeypatch.setattr(bootstrap_first_admin, "init_db", lambda: None)

    def raise_http(db, user):
        raise HTTPException(status_code=503, detail="Firebase authentication is not configured on this server.")

    monkeypatch.setattr(bootstrap_first_admin, "bootstrap_first_admin", raise_http)

    code = bootstrap_first_admin.main()

    assert code == 1
    captured = capsys.readouterr()
    assert "First administrator provisioning failed: Firebase authentication is not configured on this server." in captured.err


def test_cli_generic_exception_masks_secrets(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "admin@college.edu"])

    mock_app = SimpleNamespace(project_id="hydroguard-4a606")
    mock_fb_user = SimpleNamespace(uid="uid-1", email="admin@college.edu", email_verified=True)
    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: None)
    monkeypatch.setattr(bootstrap_first_admin.firebase_auth, "get_user_by_email", lambda email, app: mock_fb_user)
    monkeypatch.setattr(bootstrap_first_admin, "init_db", lambda: None)

    def raise_db_err(db, user):
        raise ConnectionError("Failed to connect to postgresql://user:supersecretpass@db.example.com/hydroguard")

    monkeypatch.setattr(bootstrap_first_admin, "bootstrap_first_admin", raise_db_err)

    code = bootstrap_first_admin.main()

    assert code == 1
    captured = capsys.readouterr()
    assert "supersecretpass" not in captured.err
    assert "First administrator provisioning failed (ConnectionError)" in captured.err


def test_cli_successful_run(capsys, monkeypatch):
    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.setattr(sys, "argv", ["bootstrap_first_admin.py", "mail4dssr@gmail.com"])

    mock_app = SimpleNamespace(project_id="hydroguard-4a606")
    mock_fb_user = SimpleNamespace(uid="target-firebase-uid", email="mail4dssr@gmail.com", email_verified=True)
    deleted = []

    monkeypatch.setattr(bootstrap_first_admin, "_firebase_app", lambda: mock_app)
    monkeypatch.setattr(bootstrap_first_admin.firebase_admin, "delete_app", lambda app: deleted.append(app))
    monkeypatch.setattr(bootstrap_first_admin.firebase_auth, "get_user_by_email", lambda email, app: mock_fb_user)
    monkeypatch.setattr(bootstrap_first_admin, "init_db", lambda: None)

    mock_account = SimpleNamespace(firebase_uid="target-firebase-uid", email="mail4dssr@gmail.com", role="ADMIN")
    monkeypatch.setattr(bootstrap_first_admin, "bootstrap_first_admin", lambda db, user: mock_account)

    code = bootstrap_first_admin.main()

    assert code == 0
    captured = capsys.readouterr()
    assert "Target database:" in captured.out
    assert "First HydroGuard administrator provisioned. Firebase UID: target-firebase-uid" in captured.out
    assert deleted == [mock_app]
