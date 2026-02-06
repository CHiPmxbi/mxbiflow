from dataclasses import dataclass
from pathlib import Path
from random import choice

from pygame import Event, Rect, Surface, image, transform

from mxbiflow import get_mxbiflow

ASSETS_PATH = Path(__file__).parent / "assets"


@dataclass
class Asset:
    image: Surface
    rect: Rect


class IDLE:
    _running: bool

    def __init__(self) -> None:
        self._mxbiflow = get_mxbiflow()

        self._screen_size = self._mxbiflow.mxbi.screen_size
        self._pos = ((self._screen_size.width // 4) * 3, self._screen_size.height // 2)
        self._vstimulus_size = self._screen_size.width // 2 * 0.75

        self._assets = [
            Asset(
                asset_image := transform.scale(
                    image.load(path).convert_alpha(),
                    (self._vstimulus_size, self._vstimulus_size),
                ),
                asset_image.get_rect(center=self._pos),
            )
            for path in ASSETS_PATH.glob("*.png")
        ]

        self._asset = choice(self._assets)

    def start(self) -> None:
        self._running = True

    def quit(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def handle_event(self, event: Event) -> None: ...

    def update(self, dt_s: float) -> None: ...

    def draw(self, screen: Surface) -> None:
        screen.blit(self._asset.image, self._asset.rect)
