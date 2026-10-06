"""Keep all backend tests away from the persistent development database."""

import os
import tempfile
from pathlib import Path


_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / f"hydroguard-pytest-{os.getpid()}.sqlite"
os.environ["HYDROGUARD_DATABASE_PATH"] = str(_TEST_DATABASE_PATH)


def pytest_sessionfinish(session, exitstatus):
    from app.db.database import engine

    engine.dispose()
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{_TEST_DATABASE_PATH}{suffix}").unlink(missing_ok=True)
