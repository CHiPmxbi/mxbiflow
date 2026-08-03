from pathlib import Path

from pygame.image import load
from pygame.sprite import Sprite
from pygame.transform import scale


class ImageSprite(Sprite):
    def __init__(
        self, path: Path, size: int | None = None, pos: tuple[int, int] = (0, 0)
    ) -> None:
        super().__init__()

        raw_image = load(path)

        if size is not None:
            self.image = scale(raw_image, (size, size))
        else:
            self.image = raw_image

        self.rect = self.image.get_rect(center=pos)
