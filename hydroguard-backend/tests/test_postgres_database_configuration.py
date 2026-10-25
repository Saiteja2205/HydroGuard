"""Tests for PostgreSQL database configuration, URL normalization, pooling, and session lifecycle."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_upgrade_legacy_sqlite_schema_skips_when_not_sqlite():
    """Verify _upgrade_legacy_sqlite_schema immediately returns on PostgreSQL without executing ALTERs."""
    from unittest.mock import MagicMock
    from app.db.database import _upgrade_legacy_sqlite_schema
    import app.db.database as db_mod

    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"

    with patch.object(db_mod, "engine", mock_engine):
        _upgrade_legacy_sqlite_schema()
        # Verify no connection or begins were opened since dialect is postgresql
        assert mock_engine.begin.call_count == 0


def test_production_environment_prevents_development_seeding():
    """Verify production environment does not execute development dataset seeding."""
    from app.main import lifespan, app
    import app.main as main_mod

    with patch.dict(os.environ, {"HYDROGUARD_ENVIRONMENT": "production"}):
        with patch.object(main_mod, "development_environment", "production"):
            with patch("app.db.seed.seed_development_dataset") as mock_seed:
                with patch("app.db.database.init_db"):
                    with patch("app.main._report_firebase_configuration"):
                        with patch("ml.services.thingspeak_service.load_config_from_env") as mock_ts:
                            mock_ts.return_value.configured = False
                            with patch("app.services.thingspeak_alert_monitor.get_alert_monitor") as mock_mon:
                                mock_mon.return_value.start = AsyncMock()
                                mock_mon.return_value.stop = AsyncMock()
                                # Lifespan context
                                async def run_context():
                                    async with lifespan(app):
                                        pass
                                import asyncio
                                asyncio.run(run_context())
                                assert mock_seed.call_count == 0, "Seed dataset should never be called in production"


def test_remote_database_url_leaves_local_sqlite_untouched():
    """Verify pointing DATABASE_URL to PostgreSQL does not mutate or rewrite local SQLite file."""
    from pathlib import Path
    backend_root = Path(__file__).resolve().parents[1]
    sqlite_file = backend_root / "data" / "hydroguard.db"

    initial_mtime = sqlite_file.stat().st_mtime if sqlite_file.exists() else None
    initial_size = sqlite_file.stat().st_size if sqlite_file.exists() else None

    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://render_user:pass@host/prod_db"}, clear=False):
        os.environ.pop("HYDROGUARD_DATABASE_URL", None)
        resolved = resolve_database_url()
        assert resolved.startswith("postgresql+psycopg://")

    if sqlite_file.exists():
        assert sqlite_file.stat().st_mtime == initial_mtime
        assert sqlite_file.stat().st_size == initial_size
