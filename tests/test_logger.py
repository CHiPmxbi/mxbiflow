"""Tests for mxbiflow.utils.logger."""

import json
import logging
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from loguru import logger as loguru_logger

from mxbiflow.core.path import get_default_log_file_path, set_base_path
from mxbiflow.utils.logger import logger, rfid_logger, setup_logging


class LoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        # Save and clear loguru's global handlers to isolate each test.
        core = cast(Any, loguru_logger)._core
        self._saved_loguru_handlers = dict(core.handlers)
        core.handlers.clear()

        self._root = logging.getLogger()
        self._saved_root_handlers = list(self._root.handlers)

    def tearDown(self) -> None:
        loguru_logger.remove()
        core = cast(Any, loguru_logger)._core
        core.handlers.clear()
        core.handlers.update(self._saved_loguru_handlers)

        self._root.handlers[:] = self._saved_root_handlers

    def test_import_mxbiflow_does_not_touch_loguru(self) -> None:
        """Importing the library must not configure loguru globally."""
        code = textwrap.dedent(
            """
            import loguru

            before = set(loguru.logger._core.handlers)
            import mxbiflow
            after = set(loguru.logger._core.handlers)

            assert before == after, f"loguru handlers changed: {before} -> {after}"
            print("SIDE_EFFECT_FREE")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("SIDE_EFFECT_FREE", result.stdout)

    def test_setup_logging_bridges_stdlib_records_to_loguru(self) -> None:
        """setup_logging() must route stdlib records through loguru."""
        records: list[str] = []

        setup_logging(level="DEBUG", log_file=None)
        loguru_logger.remove()
        loguru_logger.add(records.append, format="{message}")

        logger.info("bridged %s", "record")

        self.assertEqual([m.rstrip("\n") for m in records], ["bridged record"])

    def test_setup_logging_uses_default_log_file(self) -> None:
        with TemporaryDirectory() as directory:
            set_base_path(directory)

            setup_logging(level="INFO")
            loguru_logger.info("default file record")

            log_file = Path(directory) / "log" / "mxbi.log"
            self.assertEqual(get_default_log_file_path(), log_file)
            self.assertIn("default file record", log_file.read_text(encoding="utf-8"))
            loguru_logger.remove()

    def test_default_records_reach_user_stdlib_handler(self) -> None:
        """Without setup_logging(), user stdlib handlers still receive records."""
        records: list[logging.LogRecord] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = CaptureHandler()
        logger.addHandler(handler)
        try:
            logger.warning("user %s", "handler")
        finally:
            logger.removeHandler(handler)

        self.assertEqual([r.getMessage() for r in records], ["user handler"])

    def test_rfid_file_filters_records_and_preserves_fields_without_duplicates(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            main = Path(directory) / "mxbi.log"
            for _ in range(2):
                setup_logging(log_file=main)
            logger.info("general event")
            rfid_logger.info("tag event", extra={"animal_id": "A", "port": "test-port"})
            records = [
                json.loads(line)["record"]
                for line in main.with_name("rfid.log").read_text().splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["message"], "tag event")
            self.assertEqual(
                records[0]["extra"],
                {
                    "logger_name": "mxbiflow.rfid",
                    "animal_id": "A",
                    "port": "test-port",
                },
            )
            self.assertIn("tag event", main.read_text())
            self.assertIn("general event", main.read_text())
            loguru_logger.remove()

    def test_explicit_rfid_path_works_without_main_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "custom.log"
            setup_logging(log_file=None, rfid_log_file=path)
            rfid_logger.info("independent record")
            self.assertIn("independent record", path.read_text())
            self.assertEqual(list(Path(directory).iterdir()), [path])
            loguru_logger.remove()

    def test_rfid_file_can_be_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mxbi.log"
            setup_logging(log_file=path, rfid_log_file=None)
            rfid_logger.info("main only")
            self.assertFalse(path.with_name("rfid.log").exists())
            setup_logging(log_file=None)
            self.assertEqual(len(cast(Any, loguru_logger)._core.handlers), 1)


if __name__ == "__main__":
    unittest.main()
