from __future__ import annotations

import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 310_000
LEGACY_PBKDF2_ITERATIONS = 120_000
MAX_PBKDF2_ITERATIONS = 1_000_000


def _parse_password_hash(password_hash: object) -> tuple[int, bytes, bytes] | None:
    if not isinstance(password_hash, str):
        return None
    parts = password_hash.split("$")
    if len(parts) != 4:
        return None
    algorithm, iterations_text, salt_hex, digest_hex = parts
    if algorithm != "pbkdf2_sha256" or not iterations_text.isascii() or not iterations_text.isdecimal():
        return None
    try:
        iterations = int(iterations_text)
    except (TypeError, ValueError, OverflowError):
        return None
    if iterations <= 0 or iterations > MAX_PBKDF2_ITERATIONS:
        return None
    if len(salt_hex) != 32 or len(digest_hex) != hashlib.sha256().digest_size * 2:
        return None
    if not salt_hex.isascii() or not digest_hex.isascii():
        return None
    if not all(character in "0123456789abcdefABCDEF" for character in salt_hex + digest_hex):
        return None
    try:
        salt = bytes.fromhex(salt_hex)
        digest = bytes.fromhex(digest_hex)
    except (TypeError, ValueError, OverflowError):
        return None
    return iterations, salt, digest


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("password is required")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if not isinstance(password, str):
        return False
    parsed = _parse_password_hash(password_hash)
    if parsed is None:
        return False
    iterations, salt, digest = parsed
    try:
        expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    except (TypeError, ValueError, OverflowError):
        return False
    return hmac.compare_digest(expected, digest)


def needs_rehash(password_hash: str, *, iterations: int = PBKDF2_ITERATIONS) -> bool:
    parsed = _parse_password_hash(password_hash)
    if parsed is None:
        return True
    stored_iterations, _salt, _digest = parsed
    return stored_iterations < iterations
