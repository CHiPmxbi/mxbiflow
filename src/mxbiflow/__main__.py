from pathlib import Path

from . import get_mxbiflow, set_base_path
from .bootstrap import init_gameloop
from .core.path import get_log_path
from .scene import SceneManager
from .scene.idle.idle import IDLE
from .ui import run_session_post_processing, run_wizard
from .utils.logger import setup_logging


def main() -> None:
    set_base_path(Path.cwd())
    setup_logging(log_file=get_log_path() / "mxbi.log")

    scene_manager = SceneManager()
    scene_manager.register([IDLE])

    if not run_wizard(scene_manager):
        return

    game = init_gameloop(scene_manager)
    game.play()
    run_session_post_processing(get_mxbiflow().session, {})


if __name__ == "__main__":
    main()
