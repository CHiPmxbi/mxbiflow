from pymxbi import set_mxbi, MXBI


def main():
    from .game import Game

    run_config()
    # mxbi = build_mxbi()
    # set_mxbi(mxbi)

    # game = Game()
    # game.play()


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
    from .path import MXBI_CONFIG_PATH
    from .models.mxbi import MXBIModel, RewarderTypeEnum, DetectorTypeEnum
    from pymxbi.rewarder.rewarder import Rewarder
    from pymxbi.rewarder.mock_rewarder import MockRewarder
    from pymxbi.rewarder.pump_rewarder import PumpRewarder
    from pymxbi.peripheral.pumps.RPI_gpio_pump import RPIGpioPump
    from pymxbi.detector.detector import Detector
    from pymxbi.detector.mock_detector import MockDetector
    from pymxbi.detector.rfid_detector import RFIDDetector
    from pymxbi.peripheral.rfid.dorset_lid665v42 import DorsetLID665v42

    animals: list = ["001"]
    animals_db: dict = {}

    config = Configure(MXBI_CONFIG_PATH, MXBIModel).value

    rewarders: dict[int, Rewarder] = {}
    for rewarder in config.rewarders:
        if rewarder.rewarder_type == RewarderTypeEnum.MOCK_REWARDER:
            if rewarder.enabled is not True:
                continue
            rewarders[rewarder.rewarder_id] = MockRewarder(rewarder.rewarder_id)
        elif rewarder.rewarder_type == RewarderTypeEnum.GPIO_REWARDER:
            if rewarder.enabled is not True:
                continue
            pump = RPIGpioPump(rewarder.pin)
            rewarders[rewarder.rewarder_id] = PumpRewarder(pump)

    detectors: dict[int, Detector] = {}
    for detector in config.detectors:
        if detector.detector_type == DetectorTypeEnum.MOCK_DETECTOR:
            if detector.enabled is not True:
                continue
            detectors[detector.detector_id] = MockDetector(animals)
        elif detector.detector_type == DetectorTypeEnum.RFID_DETECTOR:
            if detector.enabled is not True:
                continue
            rfid_reader = DorsetLID665v42(detector.port, detector.baudrate)
            detectors[detector.detector_id] = RFIDDetector(
                animals_db, rfid_reader, 2, 2, 5
            )

    if rewarders == {} or detectors == {}:
        raise ValueError("No rewarders or detectors enabled")

    mxbi = MXBI(rewarders, detectors)
    return mxbi
