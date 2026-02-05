from pymxbi import MXBI

from .game import Game
from .models.session import Session


def main():
    run_config()

    mxbi = build_mxbi()

    session = init_session()

    game = init_mxbiflow(mxbi, session)
    game.play()


def run_config():
    import sys

    from PySide6.QtWidgets import QApplication

    from .ui.experiment_panel import ExperimentPanel
    from .ui.mxbi_panel import MXBIPanel

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel()
    experiment_panel = ExperimentPanel()
    mxbi_panel.accepted.connect(experiment_panel.show)
    experiment_panel.accepted.connect(app.quit)

    mxbi_panel.show()

    app.exec()


def build_mxbi() -> MXBI:
    from loguru import logger
    from pymxbi import MXBIModel, build_mxbi

    from .config import Configure
    from .models.session import SessionConfig
    from .path import MXBI_CONFIG_PATH, SESSION_CONFIG_PATH

    mxbi_config = Configure(MXBI_CONFIG_PATH, MXBIModel).value
    session_config = Configure(SESSION_CONFIG_PATH, SessionConfig).value

    mxbi = build_mxbi(mxbi_config, logger)
    mxbi.register_animal(
        {animal.rfid_id: animal.name for animal in session_config.animals}
    )

    return mxbi


def init_session() -> Session:
    from .config import Configure
    from .models.animal import Animal, StageState
    from .models.session import Session, SessionConfig, DailySessionIdStore
    from .path import SESSION_CONFIG_PATH, SESSION_COUNTER_PATH

    session_config = Configure(SESSION_CONFIG_PATH, SessionConfig).value
    store = DailySessionIdStore(SESSION_COUNTER_PATH)

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
        animals=animal_dict,
    )
    session.start()
    print(session.session_id)

    return session


def init_mxbiflow(mxbi, session) -> Game:
    from .default import IDLE, Habituarion
    from .detector_bridge import DetectorBridge
    from .path import STAGE_PATH
    from .scene import SceneManager

    scene_manager = SceneManager()
    scene_manager.register(Habituarion)
    scene_manager.register(IDLE)
    scene_manager.persist(STAGE_PATH)
    detector_bridge = DetectorBridge(mxbi.detector)
    return Game(session, scene_manager, detector_bridge, mxbi)
