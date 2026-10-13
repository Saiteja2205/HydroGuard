"""Keep the pytest suite away from the real development database.

``app.db.database`` resolves ``HYDROGUARD_DATABASE_PATH`` at import time and
defaults to ``data/hydroguard.db``. Without this module the hostel and account
tests inserted their fixture rows into that real file on every run, which is why
the development database filled with repeated test complaints such as
"The sink tap is leaking continuously." and feedback headed by a raw issue UUID.

Setting the environment variable here, before any ``app.*`` import, points every
test at a throwaway database instead.
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Must be set before app.db.database is imported, because that module reads it
# once at import time and creates the engine from the result.
#
# HYDROGUARD_ENVIRONMENT is deliberately left untouched: several endpoints vary
# their behaviour on it (for example the development data-source filter in
# app/api/readings.py), and the existing suite was written against whatever the
# invoking shell provides.
os.environ.setdefault("HYDROGUARD_ALLOWED_STUDENT_DOMAINS", "vrsec.ac.in")

_TEST_DB_DIR = tempfile.mkdtemp(prefix="hydroguard-pytest-")
os.environ["HYDROGUARD_DATABASE_PATH"] = os.path.join(_TEST_DB_DIR, "hydroguard-test.db")


# ---------------------------------------------------------------------------
# Sensor-read authentication
# ---------------------------------------------------------------------------
#
# /nodes, /nodes/{id}, /nodes/{id}/alerts, /nodes/{id}/forecasts,
# /nodes/{id}/model-performance, /nodes/{id}/readings/latest and
# /nodes/{id}/readings/history now require an authenticated principal. That
# guard is deliberately exercised by tests/test_sensor_read_auth.py.
#
# The tests below it are about *data* behaviour (selection rules, provenance,
# history pagination), so they use this fixture to satisfy the guard without
# changing any environment variable. Overriding the dependency rather than
# exporting HYDROGUARD_ENVIRONMENT keeps endpoint behaviour such as
# _development_data_source() exactly as each test already set it up, which is
# why conftest.py deliberately never touches that variable.
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client():
    """A TestClient for which the sensor-read auth guard always succeeds."""
    from app.core.auth import authenticated_principal
    from app.main import app

    def _principal() -> dict:
        return {"uid": "pytest@hydroguard.local", "role": "STUDENT", "development": True}

    app.dependency_overrides[authenticated_principal] = _principal
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(authenticated_principal, None)
