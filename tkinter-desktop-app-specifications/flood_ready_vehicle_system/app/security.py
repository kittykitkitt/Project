"""Password hashing helpers built on hashlib.pbkdf2_hmac (no bcrypt needed)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from app import AuthenticationError

PBKDF2_ITERATIONS = 260_000
SALT_BYTES = 16
ALGORITHM = "sha256"


def hash_password(password: str) -> tuple[str, str]:
    """Return ``(salt_hex, hash_hex)`` for *password*.

    A new random salt is generated for every call, so the same password never
    produces the same stored value.  Plain text passwords are never stored.
    """
    if not isinstance(password, str) or not password:
        raise AuthenticationError("Password cannot be empty.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time verification of *password* against stored values."""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (TypeError, ValueError):
        return False
    if not password or not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac(
        ALGORITHM, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest, expected)


def password_problems(password: str, confirm: str | None = None) -> list[str]:
    """Small password policy helper used by the user management forms."""
    problems: list[str] = []
    if len(password) < 6:
        problems.append("Password must be at least 6 characters long.")
    if not any(char.isdigit() for char in password):
        problems.append("Password must contain at least one number.")
    if confirm is not None and password != confirm:
        problems.append("Passwords do not match.")
    return problems
