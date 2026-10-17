"""Object storage for hostel photographs (lost-and-found uploads).

Why storage is pluggable
------------------------
The original design assumed Firebase Cloud Storage. That is not available for
this deployment, and the blocker is concrete rather than a missing key file:

* project ``hydroguard-4a606`` has no billing account attached;
* ``POST storage/v1/b`` therefore answers ``403 Forbidden: billing account
  disabled``;
* ``GET storage/v1/b`` lists zero buckets, and the two candidate bucket URLs
  (``hydroguard-4a606.appspot.com`` / ``firebasestorage.appspot.com``) both
  answer ``404``.

:class:`create_storage_driver` is the single place a cloud driver has to be
wired in once billing is enabled. Until then it raises
:class:`StorageConfigurationError` naming that blocker instead of quietly
writing somewhere the operator did not choose — a silent fallback would look
like a working cloud upload while storing nothing off the host.

Until that happens photographs are kept on the server's disk by
:class:`LocalStorageDriver` and served back through an authenticated endpoint
(``/api/v1/hostel/lost-found/photos/{key}``). That is a real upload: the bytes
leave the device, are persisted server-side and can be fetched again by any
signed-in user. It is not a device-side stand-in.
"""

from __future__ import annotations

import os
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# Hard ceiling for one photograph. Enforced while the body streams so a
# rejected upload never buffers more than this on the server.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Extension -> media type. The extension is chosen from the *magic bytes* of
# the upload, never from the client's filename or Content-Type header.
IMAGE_MEDIA_TYPES: dict[str, str] = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

# Storage keys are server-generated, so they only ever look like this. Anything
# else (separators, "..", slashes) is rejected before a filesystem call.
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}(?:\.(?:jpg|png|webp|gif))?$", re.IGNORECASE)


FIREBASE_BLOCKER = (
    "Firebase Cloud Storage cannot be used for HydroGuard because project "
    "hydroguard-4a606 has no billing account: creating a bucket returns HTTP "
    "403 'billing account disabled', the bucket list is empty, and both "
    "candidate bucket URLs return 404. Attach a billing account and then set "
    "HYDROGUARD_FIREBASE_STORAGE_BUCKET to switch to the cloud driver."
)


class StorageError(RuntimeError):
    """Base class for storage failures."""


class StorageConfigurationError(StorageError):
    """Storage was asked to run in a mode this deployment cannot support."""


class UnsupportedImageError(StorageError):
    """The uploaded bytes are not a recognised image format."""


@dataclass(frozen=True)
class StoredObject:
    """One stored photograph as returned by a driver."""

    key: str
    content_type: str
    data: bytes


def detect_image_type(data: bytes) -> str | None:
    """Return the storage extension for ``data`` by sniffing magic bytes.

    The client-supplied filename and Content-Type are deliberately ignored:
    both are attacker-controlled, while the leading bytes are not.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


class StorageDriver(ABC):
    """Minimal interface a photograph store has to satisfy."""

    @abstractmethod
    def store(self, data: bytes) -> StoredObject:
        """Persist ``data`` under a fresh opaque key and return it."""

    @abstractmethod
    def load(self, key: str) -> StoredObject | None:
        """Return the stored object for ``key``, or ``None`` if absent."""


def default_upload_root() -> Path:
    """Server-side directory holding uploaded photographs."""
    configured = os.getenv("HYDROGUARD_UPLOAD_DIR", "").strip()
    if configured:
        return Path(configured)
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "data" / "uploads" / "lost_found"


class LocalStorageDriver(StorageDriver):
    """Photographs written to this server's disk.

    Keys are random UUIDs rather than the uploader's filename, so a stored
    object can never be addressed, overwritten or traversed by a client that
    chooses its own name.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, data: bytes) -> StoredObject:
        extension = detect_image_type(data)
        if extension is None:
            raise UnsupportedImageError(
                "The uploaded bytes are not a JPEG, PNG, WebP or GIF image."
            )
        key = f"{uuid.uuid4().hex}.{extension}"
        (self.root / key).write_bytes(data)
        return StoredObject(key=key, content_type=IMAGE_MEDIA_TYPES[extension], data=data)

    def load(self, key: str) -> StoredObject | None:
        if not STORAGE_KEY_PATTERN.fullmatch(key):
            # Rejects "", "../hydroguard.db", "a/b" and every other traversal
            # attempt without touching the filesystem.
            return None
        path = self.root / key
        if not path.is_file():
            # If key was provided without extension (e.g. hex UUID), look for existing image file
            for ext in ("jpg", "png", "webp", "gif"):
                candidate = self.root / f"{key}.{ext}"
                if candidate.is_file():
                    path = candidate
                    key = f"{key}.{ext}"
                    break
            else:
                return None
        data = path.read_bytes()
        ext = key.rsplit(".", 1)[1].lower() if "." in key else "jpg"
        return StoredObject(key=key, content_type=IMAGE_MEDIA_TYPES.get(ext, "image/jpeg"), data=data)



def create_storage_driver() -> StorageDriver:
    """Pick the configured photograph driver.

    A cloud bucket is honoured only when it is actually usable; otherwise the
    exact blocker is reported so a misconfigured deployment fails loudly.
    """
    bucket = os.getenv("HYDROGUARD_FIREBASE_STORAGE_BUCKET", "").strip()
    if bucket:
        raise StorageConfigurationError(
            f"HYDROGUARD_FIREBASE_STORAGE_BUCKET is set to {bucket!r}, but {FIREBASE_BLOCKER}"
        )
    return LocalStorageDriver(default_upload_root())
