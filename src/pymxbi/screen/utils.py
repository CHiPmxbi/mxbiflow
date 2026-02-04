import pyglet
from .screen import Screen


def get_screen_size() -> list[Screen]:
    display = pyglet.display.get_display()
    screens = display.get_screens()

    sizes = {
        (mode.width, mode.height) for screen in screens for mode in screen.get_modes()
    }

    sizes |= {
        (1024, 600),
        (1920, 1080),
    }

    sizes = sorted(sizes)

    return [Screen(w, h) for w, h in sizes]
