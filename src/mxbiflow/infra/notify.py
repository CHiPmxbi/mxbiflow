"""Notifications to the users subscribed to this device, through cogmoteGO."""

from pymotego import Client, Severity

# cogmote rejects bodies over 10 KB (UTF-8 bytes).
MAX_BODY_BYTES = 10 * 1024
_TRUNCATED = "\n[truncated]"


def fit_body(body: str, limit: int = MAX_BODY_BYTES) -> str:
    """Return ``body`` cut to at most ``limit`` UTF-8 bytes, marking any cut."""
    encoded = body.encode()
    if len(encoded) <= limit:
        return body
    keep = limit - len(_TRUNCATED.encode())
    return encoded[:keep].decode(errors="ignore") + _TRUNCATED


def notify(subject: str, body: str, *, severity: Severity = "info") -> None:
    """Send a plain-text notification; raises when cogmoteGO rejects it."""
    with Client() as client:
        client.notify(subject, fit_body(body), severity=severity)
