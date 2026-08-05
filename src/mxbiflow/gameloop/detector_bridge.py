from dataclasses import dataclass
from queue import Empty, SimpleQueue

import pygame
from pygame import Event, event

from mxbiflow.driver.detector import MockDetector
from mxbiflow.driver.detector.detector import DetectionResult, Detector, DetectorEvent

EVT_DETECTOR = pygame.USEREVENT + 1


@dataclass(frozen=True)
class DetectorMsg:
    kind: DetectorEvent
    animal: str | None


class DetectorBridge:
    def __init__(
        self,
        detector: Detector,
        animals_map: dict[str, str],
    ) -> None:
        self._detector = detector
        self._animals_map = animals_map
        self._q: SimpleQueue[DetectorMsg] = SimpleQueue()
        self._started = False

    def _resolve_animal(self, rfid_id: str | None) -> str | None:
        if rfid_id is None:
            return None
        return self._animals_map.get(rfid_id)

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        self._detector.begin()

        # fmt: off
        self._detector.register_event(DetectorEvent.ANIMAL_ENTERED, self._on_animal_entered)
        self._detector.register_event(DetectorEvent.ANIMAL_LEFT, self._on_animal_left)
        self._detector.register_event(DetectorEvent.UNKNOWN_ANIMAL_ENTERED, self._on_unknown_animal_entered)
        self._detector.register_event(DetectorEvent.FAULT_DETECTED, self._on_fault_detected)
        # fmt: on

    def _enqueue(self, kind: DetectorEvent, animal: str | None) -> None:
        self._q.put(DetectorMsg(kind=kind, animal=animal))

    def _on_animal_entered(self, result: DetectionResult) -> None:
        name = self._resolve_animal(result.animal_id)
        if name is None:
            self._enqueue(DetectorEvent.UNKNOWN_ANIMAL_ENTERED, result.animal_id)
            return
        self._enqueue(DetectorEvent.ANIMAL_ENTERED, name)

    def _on_animal_left(self, result: DetectionResult) -> None:
        self._enqueue(DetectorEvent.ANIMAL_LEFT, self._resolve_animal(result.animal_id))

    def _on_unknown_animal_entered(self, result: DetectionResult) -> None:
        self._enqueue(DetectorEvent.UNKNOWN_ANIMAL_ENTERED, result.animal_id)

    def _on_fault_detected(self, result: DetectionResult) -> None:
        self._enqueue(DetectorEvent.FAULT_DETECTED, result.animal_id)

    def emit_pygame_event(self) -> None:
        while True:
            try:
                msg = self._q.get_nowait()
            except Empty:
                break

            event.post(event.Event(EVT_DETECTOR, msg=msg))

    def manual_emit(self, animal_id: str | None = None) -> None:
        if isinstance(self._detector, MockDetector):
            if animal_id is None:
                self._detector.animal_left()
            else:
                self._detector.animal_present(animal_id)

    def _rfid_key_at(self, index: int) -> str | None:
        keys = list(self._animals_map.keys())
        if index < len(keys):
            return keys[index]
        return None

    def handle_event(self, event: Event) -> None:
        if event.type == pygame.KEYDOWN:
            key_map = {
                pygame.K_0: 0,
                pygame.K_1: 1,
                pygame.K_2: 2,
                pygame.K_3: 3,
                pygame.K_4: 4,
                pygame.K_5: 5,
            }
            if event.key in key_map:
                rfid_key = self._rfid_key_at(key_map[event.key])
                if rfid_key is not None:
                    self.manual_emit(rfid_key)
            elif event.key == pygame.K_l:
                self.manual_emit()
