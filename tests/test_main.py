import unittest
from unittest.mock import Mock, patch

from mxbiflow import __main__ as cli


class MainTests(unittest.TestCase):
    @patch.object(cli, "run_session_post_processing")
    @patch.object(cli, "send_crash_report")
    @patch.object(cli, "setup_logging")
    @patch.object(cli, "set_base_path")
    @patch.object(cli, "run_wizard", return_value=True)
    def test_reads_session_after_the_game_loop_sets_the_context(
        self,
        _run_wizard: Mock,
        _set_base_path: Mock,
        _setup_logging: Mock,
        send_crash_report: Mock,
        run_session_post_processing: Mock,
    ) -> None:
        session = Mock()
        context: list[Mock] = []

        def init_gameloop(_scene_manager: object) -> Mock:
            context.append(Mock(session=session))
            return Mock()

        def get_mxbiflow() -> Mock:
            if not context:
                raise RuntimeError("MXBIFlow not initialized")
            return context[0]

        with (
            patch.object(cli, "init_gameloop", side_effect=init_gameloop),
            patch.object(cli, "get_mxbiflow", side_effect=get_mxbiflow),
        ):
            cli.main()

        send_crash_report.assert_not_called()
        run_session_post_processing.assert_called_once_with(session, {})


if __name__ == "__main__":
    unittest.main()
