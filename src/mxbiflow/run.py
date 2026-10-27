"""Run an experiment: through the wizard, or headless from the cogmote configuration."""

import argparse
import json
import signal
from collections.abc import Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from threading import Thread

from .bootstrap import init_gameloop
from .core.context import MXBIFlow, get_mxbiflow
from .core.path import get_base_path
from .infra.camera_recording import CameraRecording
from .infra.cogmatrix_sync import CogMatrixRecorder
from .infra.cogmote_config import CogmoteConfigError, apply_cogmote_config
from .infra.crash_report import send_crash_report
from .infra.hardware_config import sync_hardware_config
from .infra.manifest import describe
from .infra.notify import notify
from .infra.post_processing import StagePostProcessor, deliver_session_report
from .infra.run_end import (
    COGMATRIX_STEPS,
    END_SESSION,
    SEND_REPORT,
    UPLOAD_RECORDING,
    UPLOAD_RESULTS,
    RunEnd,
    begin_run,
    publish_summary,
    run_summary,
)
from .infra.trial_status import clear_trials
from .models.session import Session
from .scene import SceneManager
from .ui import run_wizard
from .ui.run_end_screen import show_run_end
from .utils.logger import logger


def run_experiment(
    scene_manager: SceneManager,
    *,
    post_processors: Mapping[str, StagePostProcessor] | None = None,
    argv: Sequence[str] | None = None,
    max_fps: int = 60,
    recorder: CogMatrixRecorder | None = None,
) -> None:
    """Configure, play and report one run; one process run is one session.

    With ``--from-cogmote`` (in ``argv``, default ``sys.argv[1:]``) the run
    starts from the cogmote configuration without the wizard and sends the
    daily report without a dialog, so it runs as a systemd user service that
    cogmote starts and stops. A configuration that cannot start, such as an
    unknown stage, is sent as a critical notification and exits with status 1.

    Each run is recorded in CogMatrix (:class:`CogMatrixRecorder`): the session
    is created once the game loop is set up, ended and given its results when
    the game loop quits; what fails is completed in the background of a later
    run. With ``record_camera`` in the session configuration, the rig camera is
    recorded during the game loop and uploaded with the results
    (:class:`CameraRecording`). SIGTERM, as from ``systemctl stop``, ends the
    game loop like the quit command.

    After the game loop, the run summary and the steps after it (CogMatrix,
    the report) are reported to cogmote and shown on the rig screen without a
    confirm step (:mod:`mxbiflow.infra.run_end`). The report is sent when the
    session config's ``send_email`` asks for it, however the run ended.

    The hardware configuration is cogmote's current preset, else the
    device-global copy of the last one (:mod:`mxbiflow.infra.hardware_config`);
    without either the run does not start.

    ``--describe`` prints the experiment manifest (:mod:`mxbiflow.infra.manifest`)
    and returns without a window, hardware or run.
    """
    parser = argparse.ArgumentParser(description="Run the experiment.")
    parser.add_argument(
        "--from-cogmote",
        action="store_true",
        help="start from the cogmote configuration without the wizard",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the experiment manifest as JSON and exit, without a run",
    )
    args = parser.parse_args(argv)
    if args.describe:
        print(json.dumps(describe(scene_manager, get_base_path()), indent=2))
        return
    processors = post_processors or {}

    session: Session | None = None
    camera: CameraRecording | None = None
    recorder = recorder or CogMatrixRecorder()
    try:
        if args.from_cogmote:
            apply_cogmote_config(scene_manager.scenes.keys())
        sync_hardware_config()
        if not args.from_cogmote and not run_wizard(scene_manager):
            return
        game = init_gameloop(scene_manager, max_fps)
        signal.signal(signal.SIGTERM, lambda *_: game.request_quit())
        mxbiflow = get_mxbiflow()
        session = mxbiflow.session
        clear_trials()
        begin_run(session)
        recorder.start(session)
        # Earlier runs' uploads, recordings among them, must not delay this one.
        Thread(
            target=recorder.retry_pending, name="cogmatrix-retry", daemon=True
        ).start()
        if session.config.record_camera:
            camera = CameraRecording()
            camera.start()
        game.play()
        recordings = _stop_camera(camera, mxbiflow)
        camera = None
        _finish(mxbiflow, recorder, recordings, session.send_email, processors)
    except CogmoteConfigError as error:
        logger.error("run not started: %s", error)
        _report_not_started(str(error))
        raise SystemExit(1) from error
    except Exception as exc:
        send_crash_report(exc, session)
        if session is not None:
            _finish_aborted(recorder, session, camera)
        raise


def _finish(
    mxbiflow: MXBIFlow,
    recorder: CogMatrixRecorder,
    recordings: list[Path],
    send_report: bool,
    processors: Mapping[str, StagePostProcessor],
) -> None:
    session = mxbiflow.session
    summary = run_summary(session, mxbiflow.trials)
    publish_summary(summary)
    names: list[str] = []
    if recorder.recording:
        names += [END_SESSION, UPLOAD_RESULTS] + (
            [UPLOAD_RECORDING] if recordings else []
        )
    if send_report:
        names.append(SEND_REPORT)
    steps = RunEnd(names)

    def work() -> None:
        try:
            recorder.finish(session, recordings=recordings, steps=steps)
        except Exception as error:  # noqa: BLE001 - the report still goes out
            logger.exception("cannot record the run in CogMatrix")
            steps.fail(COGMATRIX_STEPS, str(error), retry=False)
        if send_report:
            steps.start(SEND_REPORT)
            try:
                steps.done(SEND_REPORT, url=deliver_session_report(session, processors))
            except Exception as error:  # noqa: BLE001 - logged by the report
                steps.fail(
                    [SEND_REPORT], str(error) or type(error).__name__, retry=False
                )

    screen = mxbiflow.mxbi.screen_size
    show_run_end(
        summary,
        steps,
        work,
        size=(screen.width, screen.height),
        fullscreen=session.fullscreen,
    )
    steps.close()


def _report_not_started(reason: str) -> None:
    try:
        notify("mxbiflow run not started", reason, severity="critical")
    except Exception:  # noqa: BLE001 - the log keeps the reason when cogmoteGO is absent
        logger.exception("cannot send the not-started notification")


def _stop_camera(camera: CameraRecording | None, mxbiflow: MXBIFlow) -> list[Path]:
    if camera is None:
        return []
    latency = timedelta(milliseconds=mxbiflow.session.config.capture_latency_ms)
    return camera.stop(mxbiflow.trials, capture_latency=latency)


def _finish_aborted(
    recorder: CogMatrixRecorder, session: Session, camera: CameraRecording | None
) -> None:
    steps = RunEnd(["run", *COGMATRIX_STEPS] if recorder.recording else ["run"])
    steps.fail(["run"], "the run crashed; see the crash report", retry=False)
    try:
        if session.start_at is not None and session.end_at is None:
            session.end()
        recorder.finish(
            session,
            aborted=True,
            recordings=_stop_camera(camera, get_mxbiflow()),
            steps=steps,
        )
    except Exception:  # noqa: BLE001 - the crash report is already out
        logger.exception("cannot record the aborted run in CogMatrix")
    finally:
        steps.close()
