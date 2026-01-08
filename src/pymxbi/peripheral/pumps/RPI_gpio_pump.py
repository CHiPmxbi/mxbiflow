"""
Author: HuYang huyangcommit@gmail.com
Date: 2026-01-06 12:21:03
LastEditors: HuYang huyangcommit@gmail.com
LastEditTime: 2026-01-08 02:12:19

Description:
This module provides :class:`RPIGpioPump`,
which controls a pump (or any on/off actuator) through a GPIO output pin using
`gpiozero.DigitalOutputDevice`

Copyright (c) 2026 by HuYang huyangcommit@gmail.com, All Rights Reserved
"""

from gpiozero import DigitalOutputDevice


class RPIGpioPump:
    """
    Control a pump using a Raspberry Pi GPIO output pin

    Control a pump using gpiozero's DigitalOutputDevice via a GPIO pin
    """

    def __init__(self, pin: int) -> None:
        """
        Initialize the GPIO pump controller on the given pin

        :param pin: GPIO pin used to control the pump
        :type pin: int
        """
        self.pin: int = pin
        try:
            self._pump = DigitalOutputDevice(pin, active_high=True, initial_value=False)
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize GPIO pump on pin {pin}: {exc}")

    def start(self) -> None:
        """
        Turn the pump on
        """
        self._pump.on()

    def stop(self) -> None:
        """
        Turn the pump off
        """
        self._pump.off()

    def close(self) -> None:
        """
        Release the GPIO resources
        """
        self._pump.close()
