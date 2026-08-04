import pygame
from pygame import Surface
from pygame.typing import ColorLike


def create_background(
    screen_size: tuple[int, int],
    border_width: int = 40,
    *,
    border_color: ColorLike = (255, 255, 255),
    background_color: ColorLike = (0, 0, 0),
) -> Surface:
    width, height = screen_size
    surface = Surface(screen_size)
    surface.fill(border_color)
    background_rect = pygame.Rect(
        border_width, border_width, width - 2 * border_width, height - 2 * border_width
    )
    pygame.draw.rect(surface, background_color, background_rect)
    return surface
