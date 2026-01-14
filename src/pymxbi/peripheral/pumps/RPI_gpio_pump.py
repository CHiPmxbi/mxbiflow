"""Raspberry Pi GPIO-backed pump implementation."""

from gpiozero import DigitalOutputDevice


class RPIGpioPump:
    """Control a pump using a Raspberry Pi GPIO output pin.

    Parameters
    ----------
    pin : int
        GPIO pin used to control the pump.
    """

    def __init__(self, pin: int) -> None:
        """Initialize the GPIO pump controller on the given pin.

        Parameters
        ----------
        pin : int
            GPIO pin used to control the pump.

        Raises
        ------
        RuntimeError
            If the GPIO pin cannot be initialized.
        """
        self.pin: int = pin
        try:
            self._pump = DigitalOutputDevice(pin, active_high=True, initial_value=False)
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize GPIO pump on pin {pin}: {exc}")

    def start(self) -> None:
        """Turn the pump on."""
        self._pump.on()

    def stop(self) -> None:
        """Turn the pump off."""
        self._pump.off()

    def close(self) -> None:
        """Release the GPIO resources."""
        self._pump.close()
