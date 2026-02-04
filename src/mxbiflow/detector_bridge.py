from dataclasses import dataclass
from queue import Empty, SimpleQueue

from pygame import Event, event
import pygame
from pymxbi.detector.detector import DetectionResult, Detector, DetectorEvent
from pymxbi.detector import MockDetector

EVT_DETECTOR = pygame.USEREVENT + 1


@dataclass(frozen=True)
class DetectorMsg:
    kind: DetectorEvent
    animal: str | None


class DetectorBridge:
    def __init__(self, detector: Detector) -> None:
        self._detector = detector
        self._q = SimpleQueue()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        self._detector.begin()
        self._detector.register_event(DetectorEvent.ANIMAL_ENTERED, self._emit_entered)
        self._detector.register_event(DetectorEvent.ANIMAL_LEFT, self._emit_left)
        self._detector.register_event(DetectorEvent.FAULT_DETECTED, self._emit_fault)

    def _emit(self, kind: DetectorEvent, animal: str | None) -> None:
        self._q.put(DetectorMsg(kind=kind, animal=animal))

    def _emit_entered(self, detection_result: DetectionResult) -> None:
        self._emit(
            DetectorEvent.ANIMAL_ENTERED,
            detection_result.animal_id or detection_result.animal_name,
        )

    def _emit_left(self, detection_result: DetectionResult) -> None:
        self._emit(
            DetectorEvent.ANIMAL_LEFT,
            detection_result.animal_id or detection_result.animal_name,
        )

    def _emit_fault(self, detection_result: DetectionResult) -> None:
        self._emit(
            DetectorEvent.FAULT_DETECTED,
            detection_result.animal_id or detection_result.animal_name,
        )

    def emit_pygame_event(self) -> None:
        while True:
            try:
                msg = self._q.get_nowait()
            except Empty:
                break

            event.post(event.Event(EVT_DETECTOR, msg=msg))

    def manaul_emit(self, animal_idx: int | None = None) -> None:
        if isinstance(self._detector, MockDetector):
            if animal_idx is None:
                self._detector.animal_left()
            else:
                self._detector.animal_present(animal_idx)

    def handle_event(self, event: Event) -> None:
        if event.type == pygame.KEYDOWN:
            match event.key:
                case pygame.K_0:
                    self.manaul_emit(0)
                case pygame.K_1:
                    self.manaul_emit(1)
                case pygame.K_2:
                    self.manaul_emit(2)
                case pygame.K_3:
                    self.manaul_emit(3)
                case pygame.K_4:
                    self.manaul_emit(4)
                case pygame.K_5:
                    self.manaul_emit(5)
                case pygame.K_l:
                    self.manaul_emit()
