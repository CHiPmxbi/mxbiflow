"""Raspberry Pi GPIO-backed pump implementation.

This module provides :class:`~pymxbi.peripheral.pumps.RPI_gpio_pump.RPIGpioPump`,
an implementation of the :class:`~pymxbi.peripheral.pumps.pump.Pump` protocol
using ``gpiozero.DigitalOutputDevice`` to switch a GPIO pin on and off.
"""

from gpiozero import DigitalOutputDevice

from pymxbi.peripheral.pumps.pump import Direction


class RPIGpioPump:
    """Control a pump using a Raspberry Pi GPIO output pin.

    Parameters
    ----------
    pin : int
        GPIO pin used to control the pump.

    Attributes
    ----------
    _pin : int
        GPIO pin used to control the pump.
    _pump : gpiozero.DigitalOutputDevice
        Underlying GPIO output device (initialized in :meth:`open`).

    Notes
    -----
    Call :meth:`open` before calling :meth:`start`, :meth:`stop`, or
    :meth:`close`.

    Direction control is not supported; :meth:`set_direction` and
    :meth:`toggle_direction` raise :class:`NotImplementedError`.
    """

    def __init__(self, pin: int) -> None:
        """Create a GPIO pump controller for the given pin.

        Parameters
        ----------
        pin : int
            GPIO pin used to control the pump.
        """
        self._pin: int = pin

    def open(self) -> None:
        """Initialize the underlying GPIO device.

        Raises
        ------
        RuntimeError
            If the GPIO output device cannot be initialized.
        """
        try:
            self._pump = DigitalOutputDevice(
                self._pin, active_high=True, initial_value=False
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialize GPIO pump on pin {self._pin}: {exc}"
            )

    def start(self) -> None:
        """Turn the pump on."""
        self._pump.on()

    def stop(self) -> None:
        """Turn the pump off."""
        self._pump.off()

    def close(self) -> None:
        """Release the GPIO resources."""
        self._pump.close()

    def set_direction(self, direction: Direction) -> None:
        """Set the pump's direction.

        Parameters
        ----------
        direction : Direction
            Desired pump direction.

        Raises
        ------
        NotImplementedError
            This pump implementation does not support direction control.
        """
        raise NotImplementedError("RPIGpioPump does not support direction control.")

    def toggle_direction(self) -> None:
        """Toggle the pump's direction.

        Raises
        ------
        NotImplementedError
            This pump implementation does not support direction control.
        """
        raise NotImplementedError("RPIGpioPump does not support direction control.")
