from pathlib import Path

from . import get_mxbiflow, set_base_path
from .bootstrap import init_gameloop
from .infra import send_crash_report
from .models.session import Session
from .scene import SceneManager
from .scene.idle.idle import IDLE
from .ui import run_session_post_processing, run_wizard
from .utils.logger import setup_logging


def main() -> None:
    set_base_path(Path.cwd())
    setup_logging()

    scene_manager = SceneManager()
    scene_manager.register([IDLE])
    session: Session | None = None
    try:
        if not run_wizard(scene_manager):
            return
        session = get_mxbiflow().session
        game = init_gameloop(scene_manager)
        game.play()
        run_session_post_processing(session, {})
    except Exception as exc:
        send_crash_report(exc, session)
        raise


if __name__ == "__main__":
    main()
