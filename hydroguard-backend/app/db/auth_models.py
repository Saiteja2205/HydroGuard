"""Persistent HydroGuard account authorization records.

Password hashing: Argon2id only.
If the argon2 C library is not installed the import will fail fast,
preventing the application from starting with a weak password scheme.
"""

from argon2 import low_level as argon2
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_salt() -> bytes:
    """Generate a random salt for Argon2id hashing."""
    import os
    return os.urandom(16)


def hash_password(plain_text: str) -> str:
    """Hash a plaintext password using Argon2id.

    The returned string is in the standard ``$argon2id$v=19$m=6,t=3,p=1$<salt>$<hash>``
    format and is compatible with the argon2 low-level API.

    Raises:
        ImportError: If argon2 is not available (should never happen because the
            dependency is enforced).
    """
    try:
        return argon2.hash_secret(
            secret=plain_text.encode() if isinstance(plain_text, str) else plain_text,
            salt=_generate_salt(),
            time_cost=3,
            memory_cost=64,
            parallelism=1,
            type=argon2.Type.ID,
            hash_len=32,
        )
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Argon2id is not available") from exc


def verify_password(plain_text: str, hash_value: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.

    Returns ``True`` if the password matches and ``False`` otherwise.

    ``argon2.low_level.verify_secret`` raises rather than returning ``False``
    when the secret does not match (``VerifyMismatchError``) or when the stored
    value is not a usable Argon2 hash (``InvalidHashError``). Both are treated
    here as a failed verification so a wrong password becomes an HTTP 401
    instead of an unhandled HTTP 500.

    Args:
        plain_text: the password entered by the user.
        hash_value: the stored hash string in Argon2id format.

    Raises:
        ImportError: If argon2 is not available.
    """
    if not hash_value:
        return False
    try:
        return argon2.verify_secret(
            secret=plain_text.encode() if isinstance(plain_text, str) else plain_text,
            hash=hash_value.encode() if isinstance(hash_value, str) else hash_value,
            type=argon2.Type.ID,
        )
    except argon2.VerificationError:
        # Wrong password or an unreadable stored hash: both are a failed login.
        return False
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Argon2id is not available") from exc


class HydroGuardUser(Base):
    """Persistent HydroGuard account authorization record.

    Uses Argon2id for password hashing. The ``password_hash`` column is
    expected to contain a string in the standard ``$argon2id$v=19$...`` format.
    """

    __tablename__ = "hydroguard_users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_hydroguard_users_email"),
        Index("idx_hydroguard_users_role_status", "role", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    invited_by_uid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)