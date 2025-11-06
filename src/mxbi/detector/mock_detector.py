from mxbi.detector.detector import DetectionResult, Detector
from mxbi.utils.logger import logger


class MockDetector(Detector):
    def __init__(self, theater) -> None:
        super().__init__(theater)

        self.__result = DetectionResult("mock_001", False)
        self._theater.root.bind("<p>", self.__on_mock_001_animal_entered)
        self._theater.root.bind("<o>", self.__on_mock_002_animal_entered)
        self._theater.root.bind("<l>", self.__on_mock_animal_left)
        self._theater.root.bind("<c>", self.__on_mock_animal_changed)
        self._theater.root.bind("<e>", self.__on_mock_error)

    def _start_detection(self) -> None:
        self.process_detection(self.__result)

    def _stop_detection(self) -> None:
        """Debug detector has no long-running resources to release."""

    def __on_mock_001_animal_entered(self, _) -> None:
        self.__result = DetectionResult("mock_001", False)
        logger.info("Mock_001 animal entered")
        self.process_detection(self.__result)

    def __on_mock_002_animal_entered(self, _) -> None:
        self.__result = DetectionResult("mock_002", False)
        logger.info("Mock_002 animal entered")
        self.process_detection(self.__result)

    def __on_mock_animal_left(self, _) -> None:
        self.__result = DetectionResult(None, False)
        logger.info("Mock animal left")
        self.process_detection(self.__result)

    def __on_mock_animal_changed(self, _) -> None:
        if self.__result.animal_name == "mock_001":
            self.__result = DetectionResult("mock_002", False)
            logger.info("Mock animal changed to mock_002")
        else:
            self.__result = DetectionResult("mock_001", False)
            logger.info("Mock animal changed to mock_001")
        self.process_detection(self.__result)

    def __on_mock_error(self, _) -> None:
        self.__result = DetectionResult(None, True)
        logger.info("detect error")
        self.process_detection(self.__result)
