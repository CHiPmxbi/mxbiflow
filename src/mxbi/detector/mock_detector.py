from mxbi.config import session_config
from mxbi.detector.detector import DetectionResult, Detector
from mxbi.utils.logger import logger


class MockDetector(Detector):
    """
    Mock detector that simulates animals entering/leaving the box.

    It now uses the animal names defined in config_session.json instead of
    hard-coded 'mock_001' / 'mock_002'.

    Keys:
      - <p>: force first animal to enter
      - <o>: force second animal to enter (if it exists)
      - <c>: toggle between configured animals
      - <l>: animal leaves
      - <e>: trigger a detector error
    """

    def __init__(self, theater) -> None:
        super().__init__(theater)

        animals_cfg = session_config.value.animals

        self._animals: list[str] = list(animals_cfg.keys())

        self._current_index: int = 0
        self.__result = DetectionResult(self._animals[self._current_index], False)

        self._theater.root.bind("<p>", self.__on_first_animal_entered)
        self._theater.root.bind("<o>", self.__on_second_animal_entered)
        self._theater.root.bind("<l>", self.__on_mock_animal_left)
        self._theater.root.bind("<c>", self.__on_mock_animal_changed)
        self._theater.root.bind("<e>", self.__on_mock_error)

    def _start_detection(self) -> None:
        animals = ", ".join(session_config.value.animals.keys()) or "<none>"
        logger.info("MockDetector started with animals: %s", animals)
        self.process_detection(self.__result)

    def _stop_detection(self) -> None:
        """Debug detector has no long-running resources to release."""
        logger.info("MockDetector stopped")

    def __on_first_animal_entered(self, _) -> None:
        """Simulate the first configured animal entering."""
        self._current_index = 0
        name = self._animals[self._current_index]
        self.__result = DetectionResult(name, False)
        logger.info("Mock animal entered (first): %s", name)
        self.process_detection(self.__result)

    def __on_second_animal_entered(self, _) -> None:
        """Simulate the second configured animal entering, if available."""
        if len(self._animals) < 2:
            logger.info("No second mock animal configured; only: %s", self._animals)
            return

        self._current_index = 1
        name = self._animals[self._current_index]
        self.__result = DetectionResult(name, False)
        logger.info("Mock animal entered (second): %s", name)
        self.process_detection(self.__result)

    def __on_mock_animal_left(self, _) -> None:
        """Simulate the current animal leaving the box."""
        self.__result = DetectionResult(None, False)
        logger.info("Mock animal left")
        self.process_detection(self.__result)

    def __on_mock_animal_changed(self, _) -> None:
        """Cycle through the configured animals."""
        if not self._animals:
            logger.info("No mock animals configured to change between.")
            return

        self._current_index = (self._current_index + 1) % len(self._animals)
        name = self._animals[self._current_index]
        self.__result = DetectionResult(name, False)
        logger.info("Mock animal changed to %s", name)
        self.process_detection(self.__result)

    def __on_mock_error(self, _) -> None:
        """Trigger an error condition from the detector."""
        self.__result = DetectionResult(None, True)
        logger.info("Mock detector error")
        self.process_detection(self.__result)
