import json
from collections.abc import Sequence
from pathlib import Path

from cyclopts import App, Parameter

from . import set_base_path
from .models.experiment import experiment_config_schema
from .run import RunFlags, run_experiment
from .scene import SceneManager
from .scene.idle.idle import IDLE
from .utils.logger import setup_logging

app = App(
    name="mxbiflow",
    help="Run an experiment, or print the schema of its configuration.",
    version_flags=[],
    default_parameter=Parameter(negative=()),
    result_action="return_value",
)


@app.command
def schema() -> None:
    """Print the JSON Schema of the cogmote experiment configuration."""
    print(json.dumps(experiment_config_schema(), indent=2))


@app.default
@app.command
def run(flags: RunFlags = RunFlags()) -> None:
    """Run the experiment (the default)."""
    set_base_path(Path.cwd())
    setup_logging()

    scene_manager = SceneManager()
    scene_manager.register([IDLE])
    run_experiment(scene_manager, argv=flags.argv())


def main(argv: Sequence[str] | None = None) -> None:
    app(argv)


if __name__ == "__main__":
    main()
