import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mxbiflow.core.path import set_base_path
from mxbiflow.driver import MXBIModel
from mxbiflow.infra import build_crash_report, send_crash_report
from mxbiflow.infra.notify import MAX_BODY_BYTES
from mxbiflow.models.session import Session, SessionConfig, SessionState


def _make_session() -> Session:
    return Session(
        config=SessionConfig(),
        mxbi_config=MXBIModel(),
        state=SessionState(),
        device_name="mxbi5",
    )


class BuildCrashReportTests(unittest.TestCase):
    def test_contains_exception_info_and_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError as exc:
            report = build_crash_report(exc, _make_session())

        self.assertEqual(report.subject, "mxbi5 Crash Report")
        self.assertIn("Crash Report - mxbi5", report.body)
        self.assertIn("Crash time:", report.body)
        self.assertIn("ValueError: boom", report.body)
        self.assertIn("test_contains_exception_info_and_traceback", report.body)
        self.assertIn("no animals configured", report.body)
        self.assertIn("Python:", report.body)
        self.assertIn("mxbiflow:", report.body)

    def test_appends_log_tail_when_present(self) -> None:
        with TemporaryDirectory() as tmp:
            set_base_path(Path(tmp))
            log_file = Path(tmp) / "log" / "mxbi.log"
            log_file.parent.mkdir()
            log_file.write_text("session log line", encoding="utf-8")

            report = build_crash_report(ValueError("x"), _make_session(), log_file)

            self.assertTrue(
                report.body.endswith("Log tail (mxbi.log):\nsession log line")
            )

    def test_log_tail_keeps_whole_last_lines_within_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "mxbi.log"
            lines = [f"line {i:05d}" for i in range(5000)]
            log_file.write_text("\n".join(lines), encoding="utf-8")

            report = build_crash_report(ValueError("x"), _make_session(), log_file)

            self.assertLessEqual(len(report.body.encode()), MAX_BODY_BYTES)
            tail = report.body.split("Log tail (mxbi.log):\n")[1]
            self.assertTrue(tail.startswith("line "))
            self.assertTrue(tail.endswith("line 04999"))

    def test_missing_log_file_is_skipped(self) -> None:
        report = build_crash_report(
            ValueError("x"), _make_session(), Path("/nonexistent/mxbi.log")
        )

        self.assertNotIn("Log tail", report.body)


class SendCrashReportTests(unittest.TestCase):
    @patch("mxbiflow.infra.crash_report.notify")
    @patch("mxbiflow.infra.crash_report.build_crash_report")
    def test_sends_built_report(
        self,
        build_report: Mock,
        notify: Mock,
    ) -> None:
        report = SimpleNamespace(subject="mxbi5 Crash Report", body="boom")
        build_report.return_value = report
        error = RuntimeError("boom")
        session = _make_session()
        log_file = Path("mxbi.log")

        send_crash_report(error, session, log_file)

        build_report.assert_called_once_with(error, session, log_file)
        notify.assert_called_once_with(report.subject, report.body, severity="critical")

    @patch("mxbiflow.infra.crash_report.get_default_log_file_path")
    @patch("mxbiflow.infra.crash_report.notify")
    @patch("mxbiflow.infra.crash_report.build_crash_report")
    def test_uses_default_log_file_when_omitted(
        self,
        build_report: Mock,
        _notify: Mock,
        get_default_log_file_path: Mock,
    ) -> None:
        error = RuntimeError("boom")
        session = _make_session()
        get_default_log_file_path.return_value = Path("log/mxbi.log")

        send_crash_report(error, session)

        build_report.assert_called_once_with(error, session, Path("log/mxbi.log"))

    @patch("mxbiflow.infra.crash_report.get_default_log_file_path")
    @patch("mxbiflow.infra.crash_report.notify")
    @patch("mxbiflow.infra.crash_report.build_crash_report")
    def test_explicit_none_disables_log_attachment(
        self,
        build_report: Mock,
        _notify: Mock,
        get_default_log_file_path: Mock,
    ) -> None:
        error = RuntimeError("boom")
        session = _make_session()

        send_crash_report(error, session, log_file=None)

        get_default_log_file_path.assert_not_called()
        build_report.assert_called_once_with(error, session, None)

    @patch("mxbiflow.infra.crash_report.notify", side_effect=RuntimeError)
    @patch("mxbiflow.infra.crash_report.build_crash_report", return_value=Mock())
    def test_send_failure_is_suppressed(
        self,
        _build_report: Mock,
        _notify: Mock,
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
