import argparse
import json
from pathlib import Path

from . import set_base_path
from .models.experiment import experiment_config_schema
from .run import run_experiment
from .scene import SceneManager
from .scene.idle.idle import IDLE
from .utils.logger import setup_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mxbiflow")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "schema", help="print the JSON Schema of the cogmote experiment configuration"
    )
    commands.add_parser(
        "run",
        add_help=False,
        help="run the experiment (the default); --from-cogmote skips the wizard",
    )
    args, rest = parser.parse_known_args(argv)
    if args.command == "schema":
        print(json.dumps(experiment_config_schema(), indent=2))
        return

    set_base_path(Path.cwd())
    setup_logging()

    scene_manager = SceneManager()
    scene_manager.register([IDLE])
    run_experiment(scene_manager, argv=rest)


if __name__ == "__main__":
    main()
