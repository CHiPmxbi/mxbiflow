from gpiozero import DigitalInputDevice
from typing import Callable


class RPIIRBreakBeamSensor:
    def __init__(self, pin: int) -> None:
        self._pin = pin
        try:
            self._sensor = DigitalInputDevice(pin, pull_up=True, active_state=False)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize IR break beam sensor on pin {pin}: {exc}"
            )

    def read(self) -> int:
        return self._sensor.value

    def close(self) -> None:
        self._sensor.close()

    def on_beam_broken(self, callback: Callable[[], None]) -> None:
        self._sensor.when_activated = callback
