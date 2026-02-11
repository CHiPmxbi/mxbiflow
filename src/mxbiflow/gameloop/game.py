import pygame
from pygame import Event
from pymxbi import MXBI

from ..core.context import MXBIFlow, set_mxbiflow
from ..models.session import Session
from ..scene import SceneManager
from .detector_bridge import DetectorBridge
from .scheduler import Scheduler


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
        if session.default_scene:
            self._scene_manager.default_scene = session.default_scene
        if session.unknown_animal_fallback:
            self._scene_manager.unknown_animal_fallback = (
                session.unknown_animal_fallback
            )
        if session.fault_fallback:
            self._scene_manager.fault_fallback = session.fault_fallback

        self._session = session
        self._mxbi = mxbi
        self._aplayer = self._mxbi.aplayer

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

        self._scene_manager.init()

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
            self._aplayer.update()
            self._scheduler.update()
            self._mxbiflow.update()

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
        if self._scene_manager.current is not None:
            self._scene_manager.current.quit()
        pygame.quit()
