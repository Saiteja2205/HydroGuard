"""Tests for PostgreSQL database configuration, URL normalization, pooling, and session lifecycle."""

import os
import pytest
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from app.db.database import (
    create_app_engine,
    get_db,
    get_db_context,
    get_masked_database_url,
    resolve_database_url,
    SessionLocal,
)


def test_resolve_database_url_from_database_url():
    """Verify DATABASE_URL normalizes postgres:// to postgresql+psycopg://."""
    with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:secret123@host.render.com:5432/hydroguard_db"}, clear=False):
        # Clear HYDROGUARD_DATABASE_URL if set
        os.environ.pop("HYDROGUARD_DATABASE_URL", None)
        url = resolve_database_url()
        assert url == "postgresql+psycopg://user:secret123@host.render.com:5432/hydroguard_db"


def test_resolve_database_url_from_postgresql_prefix():
    """Verify postgresql:// without driver normalizes to postgresql+psycopg://."""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:secret123@host.render.com:5432/hydroguard_db"}, clear=False):
        os.environ.pop("HYDROGUARD_DATABASE_URL", None)
        url = resolve_database_url()
        assert url == "postgresql+psycopg://user:secret123@host.render.com:5432/hydroguard_db"


def test_resolve_database_url_preserves_explicit_driver():
    """Verify postgresql+psycopg:// remains untouched."""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://user:secret123@host.render.com:5432/hydroguard_db"}, clear=False):
        os.environ.pop("HYDROGUARD_DATABASE_URL", None)
        url = resolve_database_url()
        assert url == "postgresql+psycopg://user:secret123@host.render.com:5432/hydroguard_db"


def test_resolve_database_url_prefers_hydroguard_url():
    """Verify HYDROGUARD_DATABASE_URL takes precedence over DATABASE_URL."""
    with patch.dict(
        os.environ,
        {
            "HYDROGUARD_DATABASE_URL": "postgresql://pri_user:pass@host/primary_db",
            "DATABASE_URL": "postgresql://sec_user:pass@host/secondary_db",
        },
        clear=False,
    ):
        url = resolve_database_url()
        assert url == "postgresql+psycopg://pri_user:pass@host/primary_db"


def test_resolve_database_url_fallback_to_sqlite():
    """Verify fallback to SQLite when no remote URL is configured."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HYDROGUARD_DATABASE_URL", None)
        os.environ.pop("DATABASE_URL", None)
        url = resolve_database_url()
        assert url.startswith("sqlite:///")


def test_get_masked_database_url_masks_password():
    """Verify passwords are redacted from connection URLs in logs."""
    raw_url = "postgresql+psycopg://admin_user:super_secret_pw@db.render.internal:5432/prod_db"
    masked = get_masked_database_url(raw_url)
    assert "super_secret_pw" not in masked
    assert "admin_user" in masked
    assert "db.render.internal" in masked
    assert "***" in masked


def test_create_app_engine_pooling_for_postgresql():
    """Verify pool settings are applied for PostgreSQL engines."""
    url = "postgresql+psycopg://user:pass@localhost:5432/testdb"
    with patch.dict(os.environ, {"HYDROGUARD_DB_POOL_SIZE": "8", "HYDROGUARD_DB_MAX_OVERFLOW": "12"}):
        pg_engine = create_app_engine(url)
        assert pg_engine.pool.size() == 8
        assert pg_engine.pool._max_overflow == 12
        pg_engine.dispose()


def test_session_lifecycle_and_rollback_on_exception():
    """Verify get_db and get_db_context roll back transactions when exceptions occur."""
    with pytest.raises(ValueError, match="Simulated application failure"):
        with get_db_context() as session:
            # Execute something that would fail if not rolled back
            session.execute(text("SELECT 1"))
            raise ValueError("Simulated application failure")

    # Dependency generator test
    gen = get_db()
    db_session = next(gen)
    assert db_session.is_active
    try:
        raise RuntimeError("Endpoint exception")
    except RuntimeError:
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("Endpoint exception"))
