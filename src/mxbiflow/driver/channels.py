"""The rig's named input and output channels, as a state machine uses them.

A machine names its channels; the rig configuration wires each name to a device or to a
GPIO pin (``channels`` of :class:`~mxbiflow.driver.MXBIModel`). Input changes carry the
time they happened, in ``time.monotonic()`` seconds.
"""

from collections.abc import Callable
from queue import Empty, SimpleQueue
from time import monotonic
from typing import Protocol

from gpiozero import DigitalInputDevice, DigitalOutputDevice

from .detector.detector import Detector
from .rewarder.rewarder import Rewarder

# The rewarder runs for a given time; a held output asks for this long and stops it.
_HOLD_MS = 600_000


class InputChannel(Protocol):
    def level(self) -> bool:
        """Whether the input is high now."""
        ...

    def changes(self) -> list[tuple[float, bool]]:
        """The changes since the last call, oldest first: when, and the new level."""
        ...

    def close(self) -> None: ...


class OutputChannel(Protocol):
    def set(self, high: bool) -> None: ...

    def close(self) -> None: ...


class DetectorInput:
    """High while the detector sees an animal; a change is seen when it is asked for."""

    def __init__(self, detector: Detector) -> None:
        self._detector = detector
        self._last = self.level()

    def level(self) -> bool:
        return self._detector.current_animal is not None

    def changes(self) -> list[tuple[float, bool]]:
        level = self.level()
        if level == self._last:
            return []
        self._last = level
        return [(monotonic(), level)]

    def close(self) -> None:
        pass


class GpioInput:
    """A GPIO pin; its edges are timed when they happen, not when they are read.

    ``pull_up`` is the pin's internal resistor: ``True`` pulls up and the input is
    high when the pin is low, ``False`` pulls down and it is high when the pin is
    high. ``None`` leaves the pin floating, and ``active_high`` then says which pin
    level is high. ``bounce_s`` ignores changes that follow one within that time.
    """

    def __init__(
        self,
        pin: int,
        *,
        pull_up: bool | None = False,
        active_high: bool | None = None,
        bounce_s: float | None = None,
    ) -> None:
        self._changes: SimpleQueue[tuple[float, bool]] = SimpleQueue()
        try:
            self._device = DigitalInputDevice(
                pin,
                # None is a floating pin; gpiozero's annotation leaves it out.
                pull_up=pull_up,  # pyright: ignore[reportArgumentType]
                active_state=active_high,
                bounce_time=bounce_s,
            )
        except Exception as exc:
            raise RuntimeError(f"cannot open GPIO input {pin}: {exc}") from exc
        self._device.when_activated = self._on(True)
        self._device.when_deactivated = self._on(False)

    def _on(self, high: bool) -> Callable[[], None]:
        return lambda: self._changes.put((monotonic(), high))

    def level(self) -> bool:
        return bool(self._device.value)

    def changes(self) -> list[tuple[float, bool]]:
        found: list[tuple[float, bool]] = []
        while True:
            try:
                found.append(self._changes.get_nowait())
            except Empty:
                return found

    def close(self) -> None:
        self._device.close()


class RewarderOutput:
    """The rewarder runs while the output is high."""

    def __init__(self, rewarder: Rewarder) -> None:
        self._rewarder = rewarder

    def set(self, high: bool) -> None:
        if high:
            self._rewarder.give_reward(_HOLD_MS)
        else:
            self._rewarder.stop_reward()

    def close(self) -> None:
        pass


class GpioOutput:
    """A GPIO pin driven as the output; ``active_high=False`` drives it low when high."""

    def __init__(self, pin: int, *, active_high: bool = True) -> None:
        try:
            self._device = DigitalOutputDevice(
                pin, active_high=active_high, initial_value=False
            )
        except Exception as exc:
            raise RuntimeError(f"cannot open GPIO output {pin}: {exc}") from exc

    def set(self, high: bool) -> None:
        self._device.value = high

    def close(self) -> None:
        self._device.close()
