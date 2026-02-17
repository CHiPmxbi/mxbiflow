import pygame
from pygame import Surface


def create_background(screen_size: tuple[int, int], border_width: int = 40) -> Surface:
    width, height = screen_size
    surface = Surface(screen_size)
    surface.fill((255, 255, 255))
    black_rect = pygame.Rect(
        border_width, border_width, width - 2 * border_width, height - 2 * border_width
    )
    pygame.draw.rect(surface, (0, 0, 0), black_rect)
    return surface
