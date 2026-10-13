"""Lost-and-found photographs: real upload, validation and authenticated serving.

Covers the four things the photo flow has to get right:

* the bytes actually reach the server and come back again (round trip),
* the server decides the format from magic bytes, not from client headers,
* size and authorization are enforced server-side, independently of Android,
* only the exact reference the upload endpoint issues is accepted by the
  create-item schema.
"""

import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient

from app.core.auth import authenticated_principal
from app.core.storage import (
    FIREBASE_BLOCKER,
    MAX_IMAGE_BYTES,
    STORAGE_KEY_PATTERN,
    LocalStorageDriver,
    StorageConfigurationError,
    UnsupportedImageError,
    create_storage_driver,
    detect_image_type,
)
from app.db.database import get_db_context, init_db
from app.db.hostel_models import LostFoundItem
from app.main import app
from app.schemas.hostel import HOSTEL_PHOTO_PATH_PREFIX, LostFoundCreate

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"hydroguard-test-image-payload" * 4
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"hydroguard-test-image-payload" * 4
UPLOAD_URL = "/api/v1/hostel/lost-found/photos"


# --------------------------------------------------------------------------- #
# Storage driver
# --------------------------------------------------------------------------- #

def test_local_storage_driver_round_trips_under_opaque_keys(tmp_path):
    driver = LocalStorageDriver(tmp_path)
    stored = driver.store(JPEG_BYTES)

    assert STORAGE_KEY_PATTERN.fullmatch(stored.key)
    # The key must be server-generated: never derived from anything a client sent.
    assert uuid.UUID(stored.key.split(".")[0])
    assert stored.content_type == "image/jpeg"

    loaded = driver.load(stored.key)
    assert loaded is not None and loaded.data == JPEG_BYTES
    assert (tmp_path / stored.key).is_file()


@pytest.mark.parametrize("key", ["", ".", "..", "../hydroguard.db", "a/b.jpg", "x.txt", "../../etc/passwd"])
def test_storage_driver_refuses_anything_but_a_generated_key(tmp_path, key):
    # Every one of these must be answered without touching the filesystem.
    assert LocalStorageDriver(tmp_path).load(key) is None


def test_storage_driver_rejects_bytes_that_are_not_an_image(tmp_path):
    with pytest.raises(UnsupportedImageError):
        LocalStorageDriver(tmp_path).store(b"<?xml version='1.0'?><script/>")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (JPEG_BYTES, "jpg"),
        (PNG_BYTES, "png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
        (b"GIF89a" + b"\x00" * 16, "gif"),
        (b"MZ\x90\x00" + b"\x00" * 32, None),
        (b"hello", None),
    ],
)
def test_image_type_is_detected_from_magic_bytes(payload, expected):
    assert detect_image_type(payload) == expected


def test_driver_defaults_to_disk_and_reports_the_exact_cloud_blocker(monkeypatch, tmp_path):
    monkeypatch.delenv("HYDROGUARD_FIREBASE_STORAGE_BUCKET", raising=False)
    monkeypatch.setenv("HYDROGUARD_UPLOAD_DIR", str(tmp_path))
    assert isinstance(create_storage_driver(), LocalStorageDriver)

    # Requesting the cloud driver must fail loudly rather than silently write
    # somewhere the operator did not choose.
    monkeypatch.setenv("HYDROGUARD_FIREBASE_STORAGE_BUCKET", "hydroguard-4a606.appspot.com")
    with pytest.raises(StorageConfigurationError) as error:
        create_storage_driver()
    assert "billing account disabled" in str(error.value)
    assert "hydroguard-4a606" in str(error.value)
    assert FIREBASE_BLOCKER in str(error.value)


# --------------------------------------------------------------------------- #
# image_url schema rule
# --------------------------------------------------------------------------- #

def _item_payload(image_url=None):
    payload = {
        "kind": "FOUND",
        "title": "Blue water bottle",
        "description": "Found a blue bottle near the wash area.",
        "category": "Other",
        "location": "Block A, first floor",
        "item_date": "2026-10-05T09:00:00Z",
    }
    if image_url is not None:
        payload["image_url"] = image_url
    return payload


def test_image_reference_accepts_https_and_the_server_issued_path():
    valid_key = f"{uuid.uuid4().hex}.jpg"
    assert LostFoundCreate(**_item_payload("https://cdn.example.com/photo.jpg")).image_url == "https://cdn.example.com/photo.jpg"
    assert (
        LostFoundCreate(**_item_payload(HOSTEL_PHOTO_PATH_PREFIX + valid_key)).image_url
        == HOSTEL_PHOTO_PATH_PREFIX + valid_key
    )


@pytest.mark.parametrize(
    "image_url",
    [
        "http://example.com/photo.jpg",
        "file:///etc/passwd",
        "//example.com/photo.jpg",
        "/api/v1/hostel/lost-found/photos/../../../data/hydroguard.db",
        "/api/v1/hostel/lost-found/photos/not-a-uuid.png",
        "/some/other/path.jpg",
    ],
)
def test_image_reference_rejects_everything_else(image_url):
    with pytest.raises(Exception):
        LostFoundCreate(**_item_payload(image_url))


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #

@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Authenticated student client writing photographs to a throwaway directory."""
    init_db()
    monkeypatch.setenv("HYDROGUARD_UPLOAD_DIR", str(tmp_path))
    monkeypatch.delenv("HYDROGUARD_FIREBASE_STORAGE_BUCKET", raising=False)
    principal = {"uid": "photo-student", "role": "STUDENT"}
    monkeypatch.setitem(app.dependency_overrides, authenticated_principal, lambda: principal)
    return TestClient(app), principal


@contextmanager
def _without_override():
    """Yield a client with ``authenticated_principal`` temporarily un-redirected."""
    saved = app.dependency_overrides.pop(authenticated_principal, None)
    try:
        yield TestClient(app)
    finally:
        if saved is not None:
            app.dependency_overrides[authenticated_principal] = saved


def test_photo_upload_and_serve_require_a_signed_in_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDROGUARD_UPLOAD_DIR", str(tmp_path))
    with _without_override() as anonymous:
        assert anonymous.post(UPLOAD_URL, content=JPEG_BYTES).status_code == 401
        assert anonymous.get(UPLOAD_URL + f"/{uuid.uuid4().hex}.jpg").status_code == 401


def test_photo_upload_rejects_unknown_roles(client):
    _, principal = client
    principal.update(uid="sensor-node", role="SENSOR")
    assert client[0].post(UPLOAD_URL, content=JPEG_BYTES).status_code == 403


def test_photo_upload_rejects_empty_wrong_format_and_oversized_bodies(client):
    http, _ = client

    empty = http.post(UPLOAD_URL, content=b"")
    assert empty.status_code == 422

    wrong_type = http.post(
        UPLOAD_URL, content=b"<script>alert(1)</script>", headers={"Content-Type": "image/jpeg"}
    )
    assert wrong_type.status_code == 415

    oversized = http.post(UPLOAD_URL, content=b"\xff\xd8\xff\xe0" + b"0" * (MAX_IMAGE_BYTES + 1))
    assert oversized.status_code == 413

    # Same rejection when the length is unknown up front and only appears while
    # the body streams in.
    chunk = b"\xff\xd8\xff\xe0" + b"0" * (1024 * 1024)
    streamed = http.post(UPLOAD_URL, content=(part for part in (chunk, chunk, chunk, chunk, chunk, chunk)))
    assert streamed.status_code == 413


def test_uploaded_photo_survives_a_full_round_trip(client):
    http, _ = client
    item_id = None
    try:
        uploaded = http.post(UPLOAD_URL, content=JPEG_BYTES, headers={"Content-Type": "image/jpeg"})
        assert uploaded.status_code == 201, uploaded.text
        image_url = uploaded.json()["image_url"]
        assert image_url.startswith(HOSTEL_PHOTO_PATH_PREFIX)
        key = image_url[len(HOSTEL_PHOTO_PATH_PREFIX):]
        assert STORAGE_KEY_PATTERN.fullmatch(key)

        served = http.get(image_url)
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/jpeg")
        assert served.content == JPEG_BYTES
        assert served.headers["cache-control"].startswith("private")

        created = http.post("/api/v1/hostel/lost-found", json=_item_payload(image_url))
        assert created.status_code == 201, created.text
        item_id = created.json()["id"]
        assert created.json()["image_url"] == image_url

        listed = http.get("/api/v1/hostel/lost-found")
        assert listed.status_code == 200
        matching = [row for row in listed.json() if row["id"] == item_id]
        assert matching and matching[0]["image_url"] == image_url

        missing = http.get(UPLOAD_URL + f"/{uuid.uuid4().hex}.jpg")
        assert missing.status_code == 404
    finally:
        # This row is a test artifact, not a real complaint: keep it out of the
        # development database the app reads.
        if item_id is not None:
            with get_db_context() as db:
                db.query(LostFoundItem).filter(LostFoundItem.id == item_id).delete()
                db.commit()


def test_photo_serving_refuses_traversal_keys(client):
    http, _ = client

    # Keys that reach the route but were not issued by the upload endpoint.
    for key in ("hydroguard.db", "not-a-uuid.jpg", uuid.uuid4().hex + ".exe"):
        assert http.get(f"{UPLOAD_URL}/{key}").status_code == 404

    # Separators arrive percent-encoded and are decoded by the router before
    # load() runs, so they have to be refused there too.
    for encoded in ("%2e%2e%2fdata%2fhydroguard.db", f"{uuid.uuid4().hex}%2f%2e%2e%2fhydroguard.db"):
        assert http.get(f"{UPLOAD_URL}/{encoded}").status_code in (400, 404)
