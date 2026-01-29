import pygame
from ..infra.eventbus import event_bus


class RectCircleSprite(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: tuple[int, int],
        size: tuple[int, int],
        rect_color: tuple[int, int, int],
        circle_color: tuple[int, int, int],
        radius: int,
    ) -> None:
        super().__init__()

        width, height = size
        surface = pygame.Surface(size, pygame.SRCALPHA)

        pygame.draw.rect(surface, rect_color, (0, 0, width, height))
        pygame.draw.circle(surface, circle_color, (width // 2, height // 2), radius)

        self.image: pygame.Surface = surface
        self.rect: pygame.Rect = surface.get_rect(topleft=pos)

    def on_touch(self) -> None:
        print("hello world")
        event_bus.publish("touch")

    def handle_event(
        self, event: pygame.event.Event, screen_size: tuple[int, int]
    ) -> None:
        pos: tuple[int, int] | None = None

        if event.type == pygame.MOUSEBUTTONDOWN:
            if getattr(event, "button", 0) == 1:
                pos = event.pos

        elif event.type == pygame.FINGERDOWN:
            w, h = screen_size
            x = int(event.x * w)
            y = int(event.y * h)
            pos = (x, y)

        if pos is not None and self.rect.collidepoint(pos):
            self.on_touch()
