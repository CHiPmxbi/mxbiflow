"""Crash report generation for email notification.

Produces a self-contained HTML report (with an optional log-file
attachment) for a raised exception, so host applications can send an
expected crash-report email without duplicating context gathering.
"""

import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from platform import platform, python_version

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pymotego import EmailAttachment

from ..models.session import Session

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_MAX_LOG_BYTES = 512 * 1024


@dataclass(frozen=True)
class CrashReport:
    """An email-ready crash report."""

    subject: str
    html_body: str
    attachments: tuple[EmailAttachment, ...] = ()


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )


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
        f"pymotego: {_package_version('pymotego')}\n"
        f"pymxbi: {_package_version('pymxbi')}"
    )


def _session_context(session: Session) -> str:
    """Summary of the session's animals."""
    try:
        animals = [
            f"{animal.name} ({animal.current_stage.stage_name} level "
            f"{animal.current_stage.level}, trial {animal.trial_id})"
            for animal in session.animals.values()
        ]
        return "\n".join(animals) if animals else "no animals configured"
    except Exception:  # noqa: BLE001 - best-effort context gathering
        return "unavailable"


def _log_attachment(log_file: Path | None) -> EmailAttachment | None:
    """Attach the tail of the given log file when it exists."""
    if log_file is None or not log_file.exists():
        return None
    try:
        content = log_file.read_bytes()
        if len(content) > _MAX_LOG_BYTES:
            content = content[-_MAX_LOG_BYTES:]
        return EmailAttachment(filename=log_file.name, content=content)
    except Exception:  # noqa: BLE001 - best-effort attachment gathering
        return None


def build_crash_report(
    exc: BaseException,
    session: Session,
    log_file: Path | None = None,
) -> CrashReport:
    """Build an email-ready crash report for ``exc``. Never raises.

    ``session`` provides the mxbi identifier and animal context;
    ``log_file`` is attached to the email when it exists.
    """
    # Imported lazily: post_processing imports core.context, which would
    # form a circular import while infra/__init__ is still initializing.
    from .post_processing import HtmlComposer

    now = datetime.now(UTC)
    mxbi_id = session.mxbi_config.mxbi_id
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    section_html = (
        _get_jinja_env()
        .get_template("crash_report.html")
        .render(
            exception_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
            exception_message=str(exc) or "(no message)",
            traceback_text=traceback_text,
            environment=_environment_summary(),
            session_context=_session_context(session),
            crash_time=now.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
            hostname=mxbi_id,
        )
    )

    composer = HtmlComposer(
        title=f"Crash Report - {mxbi_id}",
        date=now.strftime("%Y-%m-%d"),
    )
    composer.add_section(section_html)

    attachment = _log_attachment(log_file)
    return CrashReport(
        subject=f"{mxbi_id} Crash Report",
        html_body=composer.html,
        attachments=(attachment,) if attachment is not None else (),
    )
