import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pymotego import EmailAttachment

from mxbiflow.core.path import set_base_path
from mxbiflow.driver import MXBIModel
from mxbiflow.infra import build_crash_report, send_crash_report
from mxbiflow.models.session import Session, SessionConfig, SessionState


def _make_session() -> Session:
    return Session(
        config=SessionConfig(),
        mxbi_config=MXBIModel(
            mxbi_id="mxbi5",
            backup_source_root_id="source",
            backup_destination_root_id="destination",
        ),
        state=SessionState(),
    )


class BuildCrashReportTests(unittest.TestCase):
    def test_contains_exception_info_and_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError as exc:
            report = build_crash_report(exc, _make_session())

        self.assertEqual(report.subject, "mxbi5 Crash Report")
        self.assertIn("Crash Report - mxbi5", report.html_body)
        self.assertIn("mxbi5", report.html_body)
        self.assertIn("Crash Time", report.html_body)
        self.assertIn("ValueError", report.html_body)
        self.assertIn("boom", report.html_body)
        self.assertIn("test_contains_exception_info_and_traceback", report.html_body)
        self.assertIn("no animals configured", report.html_body)
        self.assertIn("Python:", report.html_body)
        self.assertIn("mxbiflow:", report.html_body)

    def test_attaches_log_file_when_present(self) -> None:
        with TemporaryDirectory() as tmp:
            set_base_path(Path(tmp))
            log_file = Path(tmp) / "log" / "mxbi.log"
            log_file.parent.mkdir()
            log_file.write_text("session log line", encoding="utf-8")

            report = build_crash_report(ValueError("x"), _make_session(), log_file)

            self.assertEqual(len(report.attachments), 1)
            attachment = report.attachments[0]
            self.assertIsInstance(attachment, EmailAttachment)
            self.assertEqual(attachment.filename, "mxbi.log")
            self.assertEqual(attachment.content, b"session log line")

    def test_escapes_html_in_exception_message(self) -> None:
        exc = ValueError("<script>alert('x')</script>")
        report = build_crash_report(exc, _make_session())

        self.assertIn("&lt;script&gt;", report.html_body)
        self.assertNotIn("<script>alert", report.html_body)


class SendCrashReportTests(unittest.TestCase):
    @patch("mxbiflow.infra.crash_report.EmailClient")
    @patch("mxbiflow.infra.crash_report.build_crash_report")
    def test_sends_built_report(
        self,
        build_report: Mock,
        email_client_cls: Mock,
    ) -> None:
        report = SimpleNamespace(
            subject="mxbi5 Crash Report",
            html_body="<html>boom</html>",
            attachments=(),
        )
        build_report.return_value = report
        email_client = email_client_cls.return_value.__enter__.return_value
        error = RuntimeError("boom")
        session = _make_session()
        log_file = Path("mxbi.log")

        send_crash_report(error, session, log_file)

        build_report.assert_called_once_with(error, session, log_file)
        email_client.send.assert_called_once_with(
            subject=report.subject,
            html_body=report.html_body,
            attachments=report.attachments,
        )

    @patch("mxbiflow.infra.crash_report.EmailClient", side_effect=RuntimeError)
    @patch("mxbiflow.infra.crash_report.build_crash_report", return_value=Mock())
    def test_send_failure_is_suppressed(
        self,
        _build_report: Mock,
        _email_client_cls: Mock,
    ) -> None:
        send_crash_report(ValueError("original"), _make_session())

    @patch("mxbiflow.infra.crash_report.logger.warning")
    @patch("mxbiflow.infra.crash_report.build_crash_report")
    def test_missing_session_skips_report(
        self,
        build_report: Mock,
        warning: Mock,
    ) -> None:
        send_crash_report(RuntimeError("boom"), None)

        build_report.assert_not_called()
        warning.assert_called_once_with(
            "crash before session init; skipping crash report"
        )


if __name__ == "__main__":
    unittest.main()
