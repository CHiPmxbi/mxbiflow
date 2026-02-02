from pymxbi import MXBI


def main():
    from .config import Configure
    from .path import SESSION_CONFIG_PATH, STAGE_PATH
    from .models.session import SessionConfig, Session
    from .models.animal import Animal, TrainState
    from .game import Game
    from .scene import SceneManager
    from .default import Habituarion, IDLE
    from .detector_bridge import DetectorBridge

    run_config()
    mxbi = build_mxbi()

    session_config = Configure(SESSION_CONFIG_PATH, SessionConfig).value

    animal_dict: dict[str, Animal] = {}
    for animal_config in session_config.animals:
        train_state = TrainState(name=animal_config.stage, level=animal_config.level)
        animal_state = Animal(
            rfid_id=animal_config.rfid_id,
            name=animal_config.name,
        )
        animal_state.set_stage(train_state)
        animal_dict[animal_config.name] = animal_state

    session = Session(
        experimenter=session_config.experimenter,
        reward_type=session_config.reward_type,
        send_email=False,
        sync_data=False,
        note="",
        animals=animal_dict,
    )
    session.start()

    scene_manager = SceneManager()
    scene_manager.register(Habituarion)
    scene_manager.register(IDLE)
    scene_manager.persist(STAGE_PATH)
    detector_bridge = DetectorBridge(mxbi.detector)
    game = Game(session, scene_manager, detector_bridge, mxbi)
    game.play()


def run_config():
    import sys
    from PySide6.QtWidgets import QApplication

    from .ui.mxbi_panel import MXBIPanel
    from .ui.experiment_panel import ExperimentPanel

    app = QApplication(sys.argv)

    mxbi_panel = MXBIPanel()
    experiment_panel = ExperimentPanel()
    mxbi_panel.accepted.connect(experiment_panel.show)
    experiment_panel.accepted.connect(app.quit)

    mxbi_panel.show()

    app.exec()


def build_mxbi() -> MXBI:
    from .config import Configure
    from .path import MXBI_CONFIG_PATH, SESSION_CONFIG_PATH, OPTIONS_PATH
    from .models.mxbi import MXBIModel, RewarderTypeEnum, DetectorTypeEnum
    from .models.session import SessionConfig, Options

    from pymxbi.rewarder import Rewarder, MockRewarder, PumpRewarder
    from pymxbi.peripheral.pumps import RPIGpioPump
    from pymxbi.detector import Detector, MockDetector, RFIDDetector
    from pymxbi.peripheral.rfid import DorsetLID665v42

    from loguru import logger

    mxbi_config = Configure(MXBI_CONFIG_PATH, MXBIModel).value
    session_config = Configure(SESSION_CONFIG_PATH, SessionConfig).value
    options = Configure(OPTIONS_PATH, Options).value
    animals = [animal.name for animal in session_config.animals]

    rewarders: dict[int, Rewarder] = {}
    for rewarder in mxbi_config.rewarders:
        if rewarder.rewarder_type == RewarderTypeEnum.MOCK_REWARDER:
            if rewarder.enabled is not True:
                continue
            rewarders[rewarder.rewarder_id] = MockRewarder(logger)
        elif rewarder.rewarder_type == RewarderTypeEnum.GPIO_REWARDER:
            if rewarder.enabled is not True:
                continue
            pump = RPIGpioPump(rewarder.pin)
            rewarders[rewarder.rewarder_id] = PumpRewarder(pump)

    detectors: dict[int, Detector] = {}
    for detector in mxbi_config.detectors:
        if detector.detector_type == DetectorTypeEnum.MOCK_DETECTOR:
            if detector.enabled is not True:
                continue
            detectors[detector.detector_id] = MockDetector(animals)
        elif detector.detector_type == DetectorTypeEnum.RFID_DETECTOR:
            if detector.enabled is not True:
                continue
            rfid_reader = DorsetLID665v42(detector.port, detector.baudrate)
            detectors[detector.detector_id] = RFIDDetector(
                options.animals, rfid_reader, 2, 2, 5
            )

    if rewarders == {} or detectors == {}:
        raise ValueError("No rewarders or detectors enabled")

    mxbi = MXBI((1000, 1000), rewarders, detectors)
    return mxbi
