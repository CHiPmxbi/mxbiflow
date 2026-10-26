import unittest
from unittest.mock import Mock, patch

from mxbiflow import __main__ as cli
from mxbiflow import run
from mxbiflow.infra.cogmote_config import CogmoteConfigError
from mxbiflow.scene import SceneManager


class RunExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock()
        self.game = Mock()
        context: list[Mock] = []

        def init_gameloop(_scene_manager: object, _max_fps: int) -> Mock:
            context.append(Mock(session=self.session))
            return self.game

        def get_mxbiflow() -> Mock:
            if not context:
                raise RuntimeError("MXBIFlow not initialized")
            return context[0]

        self.patches = {
            name: patch.object(run, name, **kwargs)
            for name, kwargs in {
                "init_gameloop": {"side_effect": init_gameloop},
                "get_mxbiflow": {"side_effect": get_mxbiflow},
                "run_wizard": {"return_value": True},
                "apply_cogmote_config": {},
                "run_session_post_processing": {},
                "send_session_report": {},
                "send_crash_report": {},
                "notify": {},
                "CogMatrixRecorder": {},
                "clear_trials": {},
            }.items()
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        self.recorder = self.mocks["CogMatrixRecorder"].return_value

    def tearDown(self) -> None:
        for p in self.patches.values():
            p.stop()

    def test_wizard_run_reads_the_session_after_the_game_loop(self) -> None:
        run.run_experiment(SceneManager(), argv=[])

        self.game.play.assert_called_once_with()
        self.mocks["clear_trials"].assert_called_once_with()
        self.recorder.retry_pending.assert_called_once_with()
        self.recorder.start.assert_called_once_with(self.session)
        self.recorder.finish.assert_called_once_with(self.session)
        self.mocks["apply_cogmote_config"].assert_not_called()
        self.mocks["run_session_post_processing"].assert_called_once_with(
            self.session, {}
        )
        self.mocks["send_crash_report"].assert_not_called()

    def test_rejected_wizard_starts_nothing(self) -> None:
        self.mocks["run_wizard"].return_value = False

        run.run_experiment(SceneManager(), argv=[])

        self.mocks["init_gameloop"].assert_not_called()

    def test_headless_run_skips_the_wizard_and_dialogs(self) -> None:
        processors = {"idle": Mock()}

        run.run_experiment(
            SceneManager(), post_processors=processors, argv=["--from-cogmote"]
        )

        self.mocks["run_wizard"].assert_not_called()
        stages = self.mocks["apply_cogmote_config"].call_args.args[0]
        self.assertEqual(set(stages), {"idle"})
        self.game.play.assert_called_once_with()
        self.mocks["send_session_report"].assert_called_once_with(
            self.session, processors
        )
        self.mocks["run_session_post_processing"].assert_not_called()

    def test_unusable_config_is_notified_and_exits_1(self) -> None:
        self.mocks["apply_cogmote_config"].side_effect = CogmoteConfigError(
            "unknown stages detect"
        )

        with self.assertRaises(SystemExit) as raised:
            run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.assertEqual(raised.exception.code, 1)
        self.mocks["notify"].assert_called_once_with(
            "mxbiflow run not started", "unknown stages detect", severity="critical"
        )
        self.mocks["init_gameloop"].assert_not_called()
        self.mocks["send_crash_report"].assert_not_called()

    def test_crash_is_reported_with_the_session(self) -> None:
        self.game.play.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        error, session = self.mocks["send_crash_report"].call_args.args
        self.assertIsInstance(error, RuntimeError)
        self.assertIs(session, self.session)
        self.recorder.finish.assert_called_once_with(self.session, aborted=True)


class CliTests(unittest.TestCase):
    @patch.object(cli, "setup_logging")
    @patch.object(cli, "set_base_path")
    @patch.object(cli, "run_experiment")
    def test_run_passes_its_arguments(
        self, run_experiment: Mock, _set_base_path: Mock, _setup_logging: Mock
    ) -> None:
        cli.main(["run", "--from-cogmote"])
        cli.main([])

        self.assertEqual(
            [call.kwargs["argv"] for call in run_experiment.call_args_list],
            [["--from-cogmote"], []],
        )


if __name__ == "__main__":
    unittest.main()
