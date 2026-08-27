from .core.config_store import ConfigStore
from .core.path import (
    get_config_session_path,
    get_mxbi_config_path,
    get_runtime_state_path,
)
from .driver import MXBI, MXBIModel
from .driver import build_mxbi as build_driver_mxbi
from .gameloop.detector_bridge import DetectorBridge
from .gameloop.game import Game
from .models.animal import Animal, StageState
from .models.session import RuntimeStateStore, Session, SessionConfig, SessionState
from .scene import SceneManager
from .utils.logger import logger


def init_gameloop(scene_manager: SceneManager, max_fps: int = 60) -> Game:
    """
    Initialize the game loop with MXBI, session, and detector bridge.

    Parameters
    ----------
    scene_manager : SceneManager
        The scene manager instance to be used by the game.
    max_fps : int, optional
        Maximum frames per second for the game loop. Must be >= 1.

    Returns
    -------
    Game
        The initialized game instance ready to run.

    Notes
    -----
    This function orchestrates the initialization of all core components
    required for the MXBI game loop to function.
    """
    mxbi_config = ConfigStore(get_mxbi_config_path(), MXBIModel).value
    mxbi = build_mxbi(mxbi_config)
    session_config_store = ConfigStore(get_config_session_path(), SessionConfig)
    session = init_session(
        session_config_store.value,
        mxbi_config,
        config_store=session_config_store,
    )

    animals_map = {
        animal.config.rfid_id: animal.config.name for animal in session.animals.values()
    }
    detector_bridge = DetectorBridge(mxbi.detector, animals_map)

    return Game(
        session,
        scene_manager,
        detector_bridge,
        mxbi,
        max_fps=max_fps,
    )


def build_mxbi(mxbi_config: MXBIModel) -> MXBI:
    return build_driver_mxbi(mxbi_config, logger)


def init_session(
    session_config: SessionConfig,
    mxbi_config: MXBIModel,
    *,
    config_store: ConfigStore[SessionConfig] | None = None,
) -> Session:
    store = RuntimeStateStore(get_runtime_state_path())

    animal_dict: dict[str, Animal] = {}
    for animal_config in session_config.animals:
        train_state = StageState(
            stage_name=animal_config.stage,
            initial_level=animal_config.level,
            level=animal_config.level,
        )
        animal_state = Animal(
            config=animal_config,
            current_stage_name=train_state.stage_name,
            stages={train_state.stage_name: train_state},
        )
        animal_dict[animal_config.name] = animal_state

    session = Session(
        config=session_config,
        mxbi_config=mxbi_config,
        state=SessionState(animals=animal_dict),
    )
    session.set_session_store(store)
    if config_store is not None:
        session.set_config_store(config_store)

    return session
