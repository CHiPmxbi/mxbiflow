"""Run an experiment: through the wizard, or headless from the cogmote configuration."""

import argparse
from collections.abc import Mapping, Sequence

from .bootstrap import init_gameloop
from .core.context import get_mxbiflow
from .infra.cogmatrix_sync import CogMatrixRecorder
from .infra.cogmote_config import CogmoteConfigError, apply_cogmote_config
from .infra.crash_report import send_crash_report
from .infra.notify import notify
from .infra.post_processing import StagePostProcessor, send_session_report
from .models.session import Session
from .scene import SceneManager
from .ui import run_session_post_processing, run_wizard
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
    the game loop quits; what fails is completed at a later start.
    """
    parser = argparse.ArgumentParser(description="Run the experiment.")
    parser.add_argument(
        "--from-cogmote",
        action="store_true",
        help="start from the cogmote configuration without the wizard",
    )
    args = parser.parse_args(argv)
    processors = post_processors or {}

    session: Session | None = None
    recorder = recorder or CogMatrixRecorder()
    try:
        if args.from_cogmote:
            apply_cogmote_config(scene_manager.scenes.keys())
        elif not run_wizard(scene_manager):
            return
        game = init_gameloop(scene_manager, max_fps)
        session = get_mxbiflow().session
        recorder.retry_pending()
        recorder.start(session)
        game.play()
        recorder.finish(session)
        if args.from_cogmote:
            send_session_report(session, processors)
        else:
            run_session_post_processing(session, processors)
    except CogmoteConfigError as error:
        logger.error("run not started: %s", error)
        _report_not_started(str(error))
        raise SystemExit(1) from error
    except Exception as exc:
        send_crash_report(exc, session)
        if session is not None:
            _finish_aborted(recorder, session)
        raise


def _report_not_started(reason: str) -> None:
    try:
        notify("mxbiflow run not started", reason, severity="critical")
    except Exception:  # noqa: BLE001 - the log keeps the reason when cogmoteGO is absent
        logger.exception("cannot send the not-started notification")


def _finish_aborted(recorder: CogMatrixRecorder, session: Session) -> None:
    try:
        if session.start_at is not None and session.end_at is None:
            session.end()
        recorder.finish(session, aborted=True)
    except Exception:  # noqa: BLE001 - the crash report is already out
        logger.exception("cannot record the aborted run in CogMatrix")
