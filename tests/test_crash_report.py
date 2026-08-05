import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pymotego import EmailAttachment

from mxbiflow.core.path import set_base_path
from mxbiflow.driver import MXBIModel
from mxbiflow.infra import build_crash_report
from mxbiflow.models.session import Session, SessionConfig, SessionState


def _make_session() -> Session:
    return Session(
        config=SessionConfig(mxbi=MXBIModel(mxbi_id="mxbi5")),
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


if __name__ == "__main__":
    unittest.main()
