import pymxbi
from loguru import logger
from pymxbi import MXBI, MXBIModel

from .config_store import ConfigStore
from .detector_bridge import DetectorBridge
from .game import Game
from .models.animal import Animal, StageState
from .models.session import DailySessionIdStore, Session, SessionConfig
from .path import (
    get_config_session_path,
    get_mxbi_config_path,
    get_session_counter_path,
)
from .scene import SceneManager
from .ui.experiment_panel import ExperimentPanel
from .ui.mxbi_panel import MXBIPanel


def init_gameloop(scene_manager: SceneManager) -> Game:
    mxbi = build_mxbi()
    session = init_session()

    detector_bridge = DetectorBridge(
        mxbi.detector, {i.rfid_id: i.name for i in session.animals.values()}
    )

    return Game(session, scene_manager, detector_bridge, mxbi)


def build_mxbi() -> MXBI:

    mxbi_config = ConfigStore(get_mxbi_config_path(), MXBIModel).value

    mxbi = pymxbi.build_mxbi(mxbi_config, logger)

    return mxbi


def init_session() -> Session:
    session_config = ConfigStore(get_config_session_path(), SessionConfig).value
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
        animals=animal_dict,
    )
    session.start()

    return session


def config_wizard():
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel()
    experiment_panel = ExperimentPanel()
    mxbi_panel.accepted.connect(experiment_panel.show)
    experiment_panel.accepted.connect(app.quit)

    mxbi_panel.show()

    app.exec()
