"""Centralized keyboard shortcut registration for the game loop."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import pygame
from pygame import Event


class ManualEmitter(Protocol):
    """Minimal interface used by the detector shortcut handlers."""

    def manual_emit(self, animal_id: str | None = None) -> None: ...

    def manual_emit_by_index(self, index: int) -> None: ...


class ManualControl(Protocol):
    """Minimal interface used by the manual level/stage shortcut handlers."""

    def level_up(self) -> None: ...

    def level_down(self) -> None: ...

    def next_stage(self) -> None: ...

    def prev_stage(self) -> None: ...


@dataclass(frozen=True)
class ShortcutBinding:
    """A single registered shortcut binding."""

    key: int
    description: str
    handler: Callable[[Event], None]


class ShortcutRegistry:
    """Registry mapping pygame keys to shortcut handlers."""

    def __init__(self) -> None:
        self._bindings: dict[int, ShortcutBinding] = {}

    @property
    def bindings(self) -> Mapping[int, ShortcutBinding]:
        """Read-only view of the registered bindings keyed by pygame key."""
        return self._bindings

    def register(
        self,
        key: int,
        description: str,
        handler: Callable[[Event], None],
    ) -> None:
        """Register a shortcut for *key*, rejecting duplicate keys."""
        if key in self._bindings:
            raise ValueError(f"shortcut for key {key} is already registered")
        self._bindings[key] = ShortcutBinding(key, description, handler)

    def handle_event(self, event: Event) -> None:
        """Dispatch a KEYDOWN event to its registered handler, if any."""
        if event.type != pygame.KEYDOWN:
            return
        binding = self._bindings.get(event.key)
        if binding is not None:
            binding.handler(event)


def register_default_shortcuts(
    registry: ShortcutRegistry,
    *,
    on_quit: Callable[[], None],
    on_capture: Callable[[], None],
    detector_bridge: ManualEmitter,
    manual_control: ManualControl,
) -> None:
    """Register the built-in game, detector, and manual control shortcuts."""
    registry.register(pygame.K_ESCAPE, "Quit the game", lambda _event: on_quit())
    registry.register(pygame.K_q, "Quit the game", lambda _event: on_quit())
    registry.register(pygame.K_c, "Capture a screenshot", lambda _event: on_capture())
    for index in range(6):
        registry.register(
            pygame.K_0 + index,
            f"Simulate RFID animal {index} entering",
            lambda _event, index=index: detector_bridge.manual_emit_by_index(index),
        )
    registry.register(
        pygame.K_l,
        "Simulate RFID animal leaving",
        lambda _event: detector_bridge.manual_emit(),
    )
    registry.register(
        pygame.K_LEFTBRACKET,
        "Level down",
        lambda _event: manual_control.level_down(),
    )
    registry.register(
        pygame.K_RIGHTBRACKET,
        "Level up",
        lambda _event: manual_control.level_up(),
    )
    registry.register(
        pygame.K_COMMA,
        "Previous stage",
        lambda _event: manual_control.prev_stage(),
    )
    registry.register(
        pygame.K_PERIOD,
        "Next stage",
        lambda _event: manual_control.next_stage(),
    )
