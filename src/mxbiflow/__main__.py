import argparse
import json
from pathlib import Path

from . import get_mxbiflow, set_base_path
from .bootstrap import init_gameloop
from .infra import send_crash_report
from .models.experiment import experiment_config_schema
from .models.session import Session
from .scene import SceneManager
from .scene.idle.idle import IDLE
from .ui import run_session_post_processing, run_wizard
from .utils.logger import setup_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mxbiflow")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "schema", help="print the JSON Schema of the cogmote experiment configuration"
    )
    args = parser.parse_args(argv)
    if args.command == "schema":
        print(json.dumps(experiment_config_schema(), indent=2))
        return

    set_base_path(Path.cwd())
    setup_logging()

    scene_manager = SceneManager()
    scene_manager.register([IDLE])
    session: Session | None = None
    try:
        if not run_wizard(scene_manager):
            return
        game = init_gameloop(scene_manager)
        session = get_mxbiflow().session
        game.play()
        run_session_post_processing(session, {})
    except Exception as exc:
        send_crash_report(exc, session)
        raise


if __name__ == "__main__":
    main()
