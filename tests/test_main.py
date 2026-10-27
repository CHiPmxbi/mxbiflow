import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from mxbiflow import __main__ as cli
from mxbiflow import run
from mxbiflow.infra.cogmote_config import CogmoteConfigError
from mxbiflow.infra.hardware_config import HardwareConfigError
from mxbiflow.scene import SceneManager


class RunExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock()
        self.session.config.record_camera = False
        self.session.config.capture_latency_ms = 40
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
                "sync_hardware_config": {},
                "deliver_session_report": {"return_value": "https://mote/r/1"},
                "begin_run": {},
                "publish_summary": {},
                "run_summary": {},
                "RunEnd": {},
                "show_run_end": {"side_effect": lambda _s, _t, work, **_kw: work()},
                "send_crash_report": {},
                "notify": {},
                "CogMatrixRecorder": {},
                "clear_trials": {},
                "CameraRecording": {},
                "signal": {},
                "Thread": {},
            }.items()
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}
        self.recorder = self.mocks["CogMatrixRecorder"].return_value
        self.camera = self.mocks["CameraRecording"].return_value
        self.steps = self.mocks["RunEnd"].return_value

    def tearDown(self) -> None:
        for p in self.patches.values():
            p.stop()

    def test_wizard_run_reads_the_session_after_the_game_loop(self) -> None:
        run.run_experiment(SceneManager(), argv=[])

        self.game.play.assert_called_once_with()
        self.mocks["clear_trials"].assert_called_once_with()
        self.mocks["Thread"].assert_called_once_with(
            target=self.recorder.retry_pending, name="cogmatrix-retry", daemon=True
        )
        self.recorder.start.assert_called_once_with(self.session)
        self.mocks["begin_run"].assert_called_once_with(self.session)
        self.recorder.finish.assert_called_once_with(
            self.session, recordings=[], steps=self.steps
        )
        self.mocks["CameraRecording"].assert_not_called()
        self.mocks["apply_cogmote_config"].assert_not_called()
        self.mocks["send_crash_report"].assert_not_called()
        self.steps.close.assert_called_once_with()

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
        self.mocks["publish_summary"].assert_called_once_with(
            self.mocks["run_summary"].return_value
        )
        self.mocks["deliver_session_report"].assert_called_once_with(
            self.session, processors
        )
        self.steps.done.assert_any_call("send_report", url="https://mote/r/1")

    def test_without_send_email_no_report_is_sent(self) -> None:
        self.session.send_email = False

        run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.mocks["deliver_session_report"].assert_not_called()
        names = self.mocks["RunEnd"].call_args.args[0]
        self.assertEqual(names, ["end_session", "upload_results"])

    def test_a_failed_report_is_a_failed_step(self) -> None:
        self.session.send_email = True
        self.mocks["deliver_session_report"].side_effect = ConnectionError("offline")

        run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.steps.fail.assert_called_once_with(["send_report"], "offline", retry=False)
        self.steps.close.assert_called_once_with()

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

    def test_missing_hardware_config_is_notified_and_exits_1(self) -> None:
        self.mocks["init_gameloop"].side_effect = HardwareConfigError(
            "no hardware configuration"
        )

        with self.assertRaises(SystemExit):
            run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.mocks["sync_hardware_config"].assert_called_once_with()
        self.mocks["notify"].assert_called_once_with(
            "mxbiflow run not started",
            "no hardware configuration",
            severity="critical",
        )
        self.mocks["send_crash_report"].assert_not_called()

    def test_crash_is_reported_with_the_session(self) -> None:
        self.game.play.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        error, session = self.mocks["send_crash_report"].call_args.args
        self.assertIsInstance(error, RuntimeError)
        self.assertIs(session, self.session)
        self.recorder.finish.assert_called_once_with(
            self.session, aborted=True, recordings=[], steps=self.steps
        )
        self.steps.fail.assert_called_once_with(
            ["run"], "the run crashed; see the crash report", retry=False
        )

    def test_camera_is_recorded_when_configured(self) -> None:
        self.session.config.record_camera = True
        self.camera.stop.return_value = [Path("a.mp4"), Path("a.vtt")]

        run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.camera.start.assert_called_once_with()
        trials = self.mocks["get_mxbiflow"]().trials
        self.camera.stop.assert_called_once_with(
            trials, capture_latency=timedelta(milliseconds=40)
        )
        self.recorder.finish.assert_called_once_with(
            self.session, recordings=[Path("a.mp4"), Path("a.vtt")], steps=self.steps
        )
        self.assertIn("upload_recording", self.mocks["RunEnd"].call_args.args[0])

    def test_a_crash_still_uploads_the_recording(self) -> None:
        self.session.config.record_camera = True
        self.camera.stop.return_value = [Path("a.mp4"), Path("a.vtt")]
        self.game.play.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        self.recorder.finish.assert_called_once_with(
            self.session,
            aborted=True,
            recordings=[Path("a.mp4"), Path("a.vtt")],
            steps=self.steps,
        )

    def test_sigterm_ends_the_game_loop(self) -> None:
        run.run_experiment(SceneManager(), argv=["--from-cogmote"])

        signum, handler = self.mocks["signal"].signal.call_args.args
        self.assertIs(signum, self.mocks["signal"].SIGTERM)
        handler(15, None)
        self.game.request_quit.assert_called_once_with()


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
