from datetime import UTC, datetime

import pygame
from pygame import Event
from pymxbi import MXBI

from ..core.context import MXBIFlow, set_mxbiflow
from ..core.path import get_data_dir_path
from ..infra.data_logger import DataLogger, DataLoggerType
from ..models.session import Session
from ..scene import SceneManager
from ..utils.logger import logger
from .detector_bridge import DetectorBridge
from .scheduler import Scheduler


class Game:
    def __init__(
        self,
        session: Session,
        scene_manager: SceneManager,
        detector_bridge: DetectorBridge,
        mxbi: MXBI,
        max_fps: int = 60,
    ) -> None:
        if max_fps < 1:
            raise ValueError(f"max_fps must be >= 1, got {max_fps}")

        if not pygame.display.get_init():
            pygame.display.init()

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

        flags = 0
        if session.fullscreen:
            flags |= pygame.FULLSCREEN

        self._screen = pygame.display.set_mode(
            (self._mxbi.screen_size.width, self._mxbi.screen_size.height),
            flags,
        )

        if session.hide_cursor:
            pygame.mouse.set_visible(False)

        self._clock = pygame.time.Clock()
        self._max_fps = max_fps
        self._running = True

        self._mxbi.begin()
        self._scene_manager.init()

        self._session.start()
        self._session_logger = DataLogger(
            path=get_data_dir_path(),
            session_id=self._session.session_id,
            filename="session",
            type=DataLoggerType.JSON,
        )
        self._session_logger.save(self._session.model_dump(mode="json"))

    def play(self) -> None:
        while self._running:
            dt = self._clock.tick(self._max_fps) / 1000.0

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
            case pygame.K_c:
                self._capture_screen()

    def _capture_screen(self) -> None:
        screenshot_dir = self._session_logger.path.parent / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        screenshot_path = screenshot_dir / f"screen_{timestamp}.png"

        pygame.image.save(self._screen, screenshot_path)
        logger.info(f"screen captured: {screenshot_path}")

    def quit(self) -> None:
        self._session.end()
        self._session_logger.save(self._session.model_dump(mode="json"))

        if self._scene_manager.current is not None:
            self._scene_manager.current.quit()
        self._mxbi.quit()
        if pygame.display.get_init():
            pygame.display.quit()
