from pathlib import Path

from mxbiflow import set_base_path
from mxbiflow.bootstrap import init_gameloop
from mxbiflow.infra.post_processing import PostProcessor
from mxbiflow.scene import SceneManager
from mxbiflow.scene.idle.idle import IDLE
from mxbiflow.ui.wizard import config_wizard


def main() -> None:
    set_base_path(Path.cwd())

    scene_manager = SceneManager()
    scene_manager.register([IDLE])

    config_wizard(scene_manager)

    game = init_gameloop(scene_manager)
    game.play()

    PostProcessor()


if __name__ == "__main__":
    main()
