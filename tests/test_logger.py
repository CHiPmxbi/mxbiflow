"""Tests for mxbiflow.utils.logger."""

import logging
import subprocess
import sys
import textwrap
import unittest
from typing import Any, cast

from loguru import logger as loguru_logger

from mxbiflow.utils.logger import logger, setup_logging


class LoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        # Save and clear loguru's global handlers to isolate each test.
        core = cast(Any, loguru_logger)._core
        self._saved_loguru_handlers = dict(core.handlers)
        core.handlers.clear()

        self._root = logging.getLogger()
        self._saved_root_handlers = list(self._root.handlers)

    def tearDown(self) -> None:
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

        setup_logging(level="DEBUG")
        loguru_logger.remove()
        loguru_logger.add(records.append, format="{message}")

        logger.info("bridged %s", "record")

        self.assertEqual([m.rstrip("\n") for m in records], ["bridged record"])

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


if __name__ == "__main__":
    unittest.main()
