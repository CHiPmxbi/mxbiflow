"""Pump-based rewarder implementation.

This module provides :class:`~pymxbi.rewarder.pump_rewarder.PumpRewarder`, an
implementation that dispenses rewards by running a pump for a given duration.
This is often used for liquid delivery, but it is not limited to liquid as long
as a pump is the appropriate actuator. Rewards are executed on a single
background worker to serialize pump access and to allow stopping the current
reward.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic, sleep

from pymxbi.peripheral.pumps.pump import Pump


class PumpRewarder:
    """Dispense pump-driven rewards via a :class:`~pymxbi.peripheral.pumps.pump.Pump`.

    The rewarder schedules reward requests on a single-thread executor. Calling
    :meth:`stop_reward` stops the currently running reward quickly; with
    ``all=True`` it also invalidates queued (not-yet-started) rewards.

    Parameters
    ----------
    pump : Pump
        Pump device used to dispense the reward.

    Attributes
    ----------
    _pump : Pump
        Underlying pump device.
    _worker : ThreadPoolExecutor
        Single worker used to serialize reward execution.
    _stop_event : threading.Event
        Event set to request stopping the currently executing reward.
    _pump_lock : threading.Lock
        Lock that serializes pump ``start``/``stop`` calls.
    _state_lock : threading.Lock
        Lock that protects internal state such as generation and closed status.
    _generation : int
        Monotonic counter used to invalidate previously queued rewards.
    _closed : bool
        Whether the rewarder has been closed and no longer accepts new rewards.
    """

    def __init__(self, pump: Pump) -> None:
        self._pump = pump
        self._worker = ThreadPoolExecutor(max_workers=1)

        self._stop_event = Event()
        self._pump_lock = Lock()

        self._state_lock = Lock()
        self._generation = 0
        self._closed = False

    def open(self) -> None:
        """Open the underlying pump."""
        self._pump.open()

    def give_reward(self, duration_ms: int) -> None:
        """Schedule dispensing a time-based reward.

        Parameters
        ----------
        duration_ms : int
            Duration to run the pump, in milliseconds. Values less than zero
            are treated as zero.

        Raises
        ------
        RuntimeError
            If the rewarder has been closed.
        """
        with self._state_lock:
            if self._closed:
                raise RuntimeError("LiquidRewarder is closed")
            gen = self._generation

        self._worker.submit(self._reward, duration_ms, gen)

    def stop_reward(self, all: bool = False) -> None:
        """Stop dispensing rewards.

        Parameters
        ----------
        all : bool, default False
            If ``False``, stop the currently executing reward as soon as
            possible. If ``True``, also invalidate any queued rewards that have
            not started yet.
        """
        self._stop_event.set()
        with self._pump_lock:
            self._pump.stop()

        if all:
            with self._state_lock:
                self._generation += 1

    def _reward(self, duration_ms: int, gen: int) -> None:
        """Execute a single reward request on the worker thread."""
        with self._state_lock:
            if self._closed or gen != self._generation:
                return

        self._stop_event.clear()

        deadline = monotonic() + max(duration_ms, 0) / 1000.0

        try:
            with self._pump_lock:
                self._pump.start()

            while not self._stop_event.is_set() and monotonic() < deadline:
                sleep(0.01)

        finally:
            with self._pump_lock:
                self._pump.stop()

    def close(self) -> None:
        """Stop any active reward and release resources.

        After closing, the rewarder rejects new rewards. This method is
        idempotent.
        """
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1

        self._stop_event.set()
        with self._pump_lock:
            self._pump.stop()

        self._worker.shutdown(wait=True)

    def give_reward_by_volume(self, volume_ul: int) -> None:
        """Dispense a volume-based reward.

        Notes
        -----
        This rewarder currently only supports time-based rewards. Use
        :meth:`give_reward` instead.
        """
        raise NotImplementedError(
            "give_reward_by_volume is not implemented for PumpRewarder"
        )

    def give_reward_by_count(self, count: int) -> None:
        """Dispense a count-based reward.

        Notes
        -----
        This rewarder currently only supports time-based rewards. Use
        :meth:`give_reward` instead.
        """
        raise NotImplementedError(
            "give_reward_by_count is not implemented for PumpRewarder"
        )
