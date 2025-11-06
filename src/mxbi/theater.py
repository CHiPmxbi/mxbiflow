from datetime import datetime
from tkinter import Canvas, Event, Tk
from typing import Callable

from mss import mss, tools

from mxbi.config import session_config
from mxbi.data_logger import DataLogger
from mxbi.models.session import SessionConfig, SessionState
from mxbi.peripheral.audio_player.controller.controller import Controller
from mxbi.peripheral.audio_player.controller.controller_factory import (
    AudioControllerEnum,
    AudioControllerFactory,
)
from mxbi.peripheral.pumps.pump_factory import PumpFactory
from mxbi.peripheral.pumps.rewarder import Rewarder
from mxbi.scheduler import Scheduler
from mxbi.utils.aplayer import APlayer
from mxbi.utils.detect_platform import PlatformEnum
from mxbi.utils.logger import logger


class Theater:
    def __init__(self) -> None:
        self._config = session_config.value
        self._session_state = SessionState(
            session_id=DataLogger.init_session_id(),
            start_time=datetime.now().timestamp(),
            session_config=self._config,
        )

        self._session_logger = DataLogger(self._session_state, "", "session_data")

        # callback for quit event
        self._on_quit: list[Callable[[], None]] = []

        self._rewarder = self._init_rewarder()
        self._acontroller = self._init_audio_controller()
        self._aplayer = APlayer(self)

        # init theater
        self._init_tk()
        self._bind_event()

        self._scheduler = Scheduler(self)
        self._scheduler.start()

    def _init_rewarder(self) -> Rewarder:
        return PumpFactory.create(self._config.pump_type)

    def _init_audio_controller(self):
        match self._config.platform:
            case PlatformEnum.RASPBERRY:
                return AudioControllerFactory.create(AudioControllerEnum.AMIXER)
            case _:
                return AudioControllerFactory.create(AudioControllerEnum.MOCK)

    def _init_tk(self) -> None:
        screen_type = session_config.value.screen_type
        self._root = Tk()

        self._root.title("mxbi")
        self._root.geometry(f"{screen_type.width}x{screen_type.height}")

        self._root.config(cursor="none")
        self._root.configure(bg="black")
        self._root.after(1000, lambda: self._root.attributes("-fullscreen", True))


    def _bind_event(self) -> None:
        self._root.bind("<Escape>", self._quit)

    def _quit(self, _: Event) -> None:
        self._session_state.end_time = datetime.now().timestamp()
        self._session_logger.save_json(self._session_state.model_dump())
        for callback in self._on_quit:
            callback()
        self._root.destroy()

    def register_event_quit(self, callback: Callable[[], None]) -> None:
        self._on_quit.append(callback)

    def caputre(self, region: Canvas):
        region.update()

        x0 = region.winfo_rootx()
        y0 = region.winfo_rooty()
        width = region.winfo_width()
        height = region.winfo_height()

        bbox = {
            "top": int(y0),
            "left": int(x0),
            "width": int(width),
            "height": int(height),
        }
        name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")

        try:
            with mss() as sct:
                sct_img = sct.grab(bbox)
                tools.to_png(sct_img.rgb, sct_img.size, output=name)
            logger.info(f"Screenshot saved: {name}")
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")

    @property
    def reward(self) -> Rewarder:
        return self._rewarder

    @property
    def aplayer(self) -> APlayer:
        return self._aplayer

    @property
    def acontroller(self) -> Controller:
        return self._acontroller

    def mainloop(self):
        self._root.mainloop()

    @property
    def root(self) -> Tk:
        return self._root

    @property
    def session_config(self) -> SessionConfig:
        return self._config


if __name__ == "__main__":
    theater = Theater()
    theater.root.mainloop()
