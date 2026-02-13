import pymxbi
from loguru import logger
from pymxbi import MXBIModel

from .core.config_store import ConfigStore
from .core.path import (
    get_config_session_path,
    get_mxbi_config_path,
    get_session_counter_path,
)
from .gameloop.detector_bridge import DetectorBridge
from .gameloop.game import Game
from .models.animal import Animal, StageState
from .models.session import DailySessionIdStore, Session, SessionConfig
from .scene import SceneManager


def init_gameloop(scene_manager: SceneManager) -> Game:
    """
    Initialize the game loop with MXBI, session, and detector bridge.

    Parameters
    ----------
    scene_manager : SceneManager
        The scene manager instance to be used by the game.

    Returns
    -------
    Game
        The initialized game instance ready to run.

    Notes
    -----
    This function orchestrates the initialization of all core components
    required for the MXBI game loop to function.
    """
    mxbi = build_mxbi()
    session_config = ConfigStore(get_config_session_path(), SessionConfig).value
    session = init_session(session_config)

    detector_bridge = DetectorBridge(
        mxbi.detector, {i.rfid_id: i.name for i in session.animals.values()}
    )

    return Game(session, scene_manager, detector_bridge, mxbi)


def build_mxbi() -> pymxbi.MXBI:
    mxbi_config = ConfigStore(get_mxbi_config_path(), MXBIModel).value
    return pymxbi.build_mxbi(mxbi_config, logger)


def init_session(session_config: SessionConfig) -> Session:
    store = DailySessionIdStore(get_session_counter_path())

    animal_dict: dict[str, Animal] = {}
    for animal_config in session_config.animals:
        train_state = StageState(
            stage_name=animal_config.stage, level=animal_config.level
        )
        animal_state = Animal(
            rfid_id=animal_config.rfid_id,
            name=animal_config.name,
        )
        animal_state.set_current_stage(train_state)
        animal_dict[animal_config.name] = animal_state

    session = Session(
        session_id=store.session_id,
        experimenter=session_config.experimenter,
        reward_type=session_config.reward_type,
        send_email=False,
        sync_data=False,
        note=session_config.note,
        default_scene=session_config.default_scene,
        unknown_animal_fallback=session_config.unknown_animal_fallback,
        fault_fallback=session_config.fault_fallback,
        hide_cursor=session_config.hide_cursor,
        fullscreen=session_config.fullscreen,
        animals=animal_dict,
    )
    session.start()

    return session
