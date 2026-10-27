"""Crash reports sent through cogmoteGO notifications.

Produces a plain-text report for a raised exception, ending with as much
of the log tail as fits, so host applications can notify the device's
subscribers without duplicating context gathering.
"""

import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from platform import platform, python_version

from loguru import logger

from ..core.path import get_default_log_file_path
from ..models.session import Session
from .notify import MAX_BODY_BYTES, notify


class _DefaultLogFile:
    pass


_DEFAULT_LOG_FILE = _DefaultLogFile()


@dataclass(frozen=True)
class CrashReport:
    """A notification-ready crash report."""

    subject: str
    body: str


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _environment_summary() -> str:
    return (
        f"Python: {python_version()}\n"
        f"Platform: {platform()}\n"
        f"mxbiflow: {_package_version('mxbiflow')}\n"
        f"pymotego: {_package_version('pymotego')}"
    )


def _session_context(session: Session) -> str:
    """Summary of the session's animals."""
    try:
        animals = [
            f"{animal.config.name} ({animal.current_stage.stage_name} level "
            f"{animal.current_stage.level}, trial {animal.trial_id})"
            for animal in session.animals.values()
        ]
        return "\n".join(animals) if animals else "no animals configured"
    except Exception:  # noqa: BLE001 - best-effort context gathering
        return "unavailable"


def _log_tail(log_file: Path | None, max_bytes: int) -> str | None:
    """Return the last whole lines of ``log_file`` within ``max_bytes``."""
    if log_file is None or max_bytes <= 0 or not log_file.exists():
        return None
    try:
        content = log_file.read_bytes()
    except Exception:  # noqa: BLE001 - best-effort log gathering
        return None
    if len(content) > max_bytes:
        content = content[-max_bytes:]
        # Drop the partial first line.
        _, _, content = content.partition(b"\n")
    return content.decode(errors="replace")


def build_crash_report(
    exc: BaseException,
    session: Session,
    log_file: Path | None = None,
) -> CrashReport:
    """Build a plain-text crash report for ``exc``. Never raises.

    ``session`` provides the device name and animal context; the tail
    of ``log_file`` fills the space left under the notification size limit.
    """
    now = datetime.now(UTC)
    mxbi_id = session.device_name
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    body = (
        f"Crash Report - {mxbi_id}\n"
        f"Crash time: {now.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"Exception: {type(exc).__module__}.{type(exc).__qualname__}: "
        f"{str(exc) or '(no message)'}\n"
        f"\nTraceback:\n{traceback_text.rstrip()}\n"
        f"\nSession:\n{_session_context(session)}\n"
        f"\nEnvironment:\n{_environment_summary()}\n"
    )

    if log_file is not None:
        heading = f"\nLog tail ({log_file.name}):\n"
        budget = MAX_BODY_BYTES - len((body + heading).encode())
        tail = _log_tail(log_file, budget)
        if tail:
            body += heading + tail

    return CrashReport(subject=f"{mxbi_id} Crash Report", body=body)


def send_crash_report(
    exc: BaseException,
    session: Session | None,
    log_file: Path | None | _DefaultLogFile = _DEFAULT_LOG_FILE,
) -> None:
    """Send a crash report without masking the original exception."""
    if session is None:
        logger.warning("crash before session init; skipping crash report")
        return

    try:
        resolved_log_file = (
            get_default_log_file_path()
            if isinstance(log_file, _DefaultLogFile)
            else log_file
        )
        report = build_crash_report(exc, session, resolved_log_file)
        notify(report.subject, report.body, severity="critical")
        logger.info("crash report sent: {}", report.subject)
    except Exception:  # noqa: BLE001 - never mask the original exception
        logger.exception("failed to send crash report")
