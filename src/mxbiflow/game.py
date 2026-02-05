import pygame
from pygame import Event

from .models.session import Session

from .scene import SceneManager
from .detector_bridge import DetectorBridge
from .scheduler import Scheduler
from pymxbi import MXBI
from .mxbiflow import set_mxbiflow, MXBIFlow


class Game:
    def __init__(
        self,
        session: Session,
        scene_manager: SceneManager,
        detector_bridge: DetectorBridge,
        mxbi: MXBI,
    ) -> None:
        pygame.init()

        self._scene_manager = scene_manager
        self._session = session
        self._mxbi = mxbi

        self._detector_binder = detector_bridge
        self._detector_binder.start()

        self._scheduler = Scheduler(self._session, self._scene_manager)

        self._mxbiflow = MXBIFlow(self._session, self._mxbi)
        set_mxbiflow(self._mxbiflow)

        self._screen = pygame.display.set_mode(
            (self._mxbi.screen_size.width, self._mxbi.screen_size.height)
        )
        self._clock = pygame.time.Clock()
        self._running = True

    def play(self) -> None:
        while self._running:
            dt = self._clock.tick(60) / 1000.0

            self._detector_binder.emit_pygame_event()

            for event in pygame.event.get():
                self._handle_event(event)
                self._scheduler.handle_event(event)
                self._scene_manager.handle_event(event)
                self._detector_binder.handle_event(event)

            self._scene_manager.update(dt)
            self._scheduler.update()

            self._screen.fill((0, 0, 0))

            self._scene_manager.draw(self._screen)
            self._scene_manager.apply_pending()

            pygame.display.flip()

        self.quit()

    def _handle_event(self, event: Event) -> None:
            match event.type:
                case pygame.QUIT:
                    self._running = False
                case pygame.KEYDOWN:
                    self._handle_keyboard_event(event)

    def _handle_keyboard_event(self, event: Event) -> None:
        match event.key:
            case pygame.K_ESCAPE:
                self._running = False
            case pygame.K_q:
                self._running = False

    def quit(self) -> None:
        pygame.quit()
