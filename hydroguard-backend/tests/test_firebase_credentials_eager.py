"""Firebase credentials are validated eagerly instead of failing on first use.

``credentials.ApplicationDefault()`` resolves lazily, so ``initialize_app()``
used to succeed with no service-account key present and every later auth call
failed with ``DefaultCredentialsError`` — which callers turned into an opaque
HTTP 503. These tests pin the eager behaviour.
"""

import sys
import types

import pytest
from fastapi import HTTPException

from app.core import auth as auth_core


def _clear_cached_app():
    """Drop the named app so the next call re-enters the initialization path."""
    import firebase_admin

    try:
        firebase_admin.delete_app(firebase_admin.get_app("hydroguard-api"))
    except ValueError:
        pass


@pytest.fixture(autouse=True)
def _isolated_firebase(monkeypatch):
    _clear_cached_app()
    yield
    _clear_cached_app()


def test_missing_project_id_fails_fast_with_actionable_detail(monkeypatch):
    monkeypatch.delenv("HYDROGUARD_FIREBASE_PROJECT_ID", raising=False)

    with pytest.raises(HTTPException) as excinfo:
        auth_core._firebase_app()

    assert excinfo.value.status_code == 503
    assert "HYDROGUARD_FIREBASE_PROJECT_ID" in excinfo.value.detail


def test_unresolvable_credentials_are_reported_eagerly(monkeypatch):
    """No credentials available -> fail on initialization, not on first login."""
    import firebase_admin

    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    # Stub google.auth so the test does not depend on the host's real ADC state.
    fake_google_auth = types.ModuleType("google.auth")

    class _DefaultCredentialsError(Exception):
        pass

    def _default(*args, **kwargs):
        raise _DefaultCredentialsError("Your default credentials were not found.")

    fake_google_auth.default = _default
    monkeypatch.setitem(sys.modules, "google.auth", fake_google_auth)

    with pytest.raises(HTTPException) as excinfo:
        auth_core._firebase_app()

    assert excinfo.value.status_code == 503
    # The client gets the actionable configuration message, never the raw cause.
    assert "GOOGLE_APPLICATION_CREDENTIALS" in excinfo.value.detail
    assert "default credentials were not found" not in excinfo.value.detail


def test_successful_initialization_returns_the_named_app(monkeypatch):
    """With credentials resolvable, the named app is created and reused."""
    import firebase_admin
    from firebase_admin import credentials as fb_credentials

    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "hydroguard-4a606")

    fake_google_auth = types.ModuleType("google.auth")
    fake_google_auth.default = lambda *a, **k: (object(), "hydroguard-4a606")
    monkeypatch.setitem(sys.modules, "google.auth", fake_google_auth)

    created = {}

    class _FakeCredential:
        def get_credential(self):
            return object()

    fake_fb_credentials = types.ModuleType("firebase_admin.credentials")
    fake_fb_credentials.ApplicationDefault = lambda: _FakeCredential()

    real_initialize_app = firebase_admin.initialize_app

    def _initialize_app(cred, options=None, name=None):
        created["name"] = name
        created["options"] = options
        return real_initialize_app(cred, options, name)

    monkeypatch.setattr(firebase_admin, "initialize_app", _initialize_app)

    app = auth_core._firebase_app()

    assert app.project_id == "hydroguard-4a606"
    assert created["name"] == "hydroguard-api"
    assert created["options"]["projectId"] == "hydroguard-4a606"

    # A second call must reuse the cached named app rather than re-initialize.
    again = auth_core._firebase_app()
    assert again is app


def test_project_mismatch_is_rejected(monkeypatch):
    import firebase_admin

    monkeypatch.setenv("HYDROGUARD_FIREBASE_PROJECT_ID", "other-project")
    monkeypatch.setattr(firebase_admin, "get_app", lambda name=None: types.SimpleNamespace(project_id="hydroguard-4a606"))

    with pytest.raises(HTTPException) as excinfo:
        auth_core._firebase_app()

    assert excinfo.value.status_code == 503
    assert "different project" in excinfo.value.detail
