"""Shared signature helpers for channel protocol verification."""

from __future__ import annotations

import hmac


def safe_compare(left: str, right: str) -> bool:
    """Constant-time comparison for secret-bearing strings."""
    return hmac.compare_digest(str(left or ""), str(right or ""))


def compute_hmac_sha256_hex(secret: str, message: str) -> str:
    """Compute lowercase hex HMAC-SHA256 signature."""
    key = (secret or "").encode("utf-8")
    data = (message or "").encode("utf-8")
    return hmac.new(key, data, "sha256").hexdigest()


def verify_hmac_sha256_hex(secret: str, message: str, signature_hex: str) -> bool:
    """Verify expected signature equals provided one in constant time."""
    expected = compute_hmac_sha256_hex(secret, message)
    return safe_compare(expected, str(signature_hex or "").lower())
