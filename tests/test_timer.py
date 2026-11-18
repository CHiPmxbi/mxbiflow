"""The timer's delays are tasks, as the audio player's sounds are."""

import unittest
from unittest.mock import patch

from mxbiflow.infra import FrameTimer
from mxbiflow.task import Task, TaskResult, TaskStatus


class FrameTimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 0
        patcher = patch("mxbiflow.infra.timer.time.get_ticks", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.timer = FrameTimer()
        self.calls: list[str] = []

    def at(self, now: int) -> None:
        self.now = now
        self.timer.update()

    def test_a_delay_calls_back_once_and_is_then_done(self) -> None:
        task = self.timer.after(delay_ms=100, callback=lambda: self.calls.append("a"))

        self.at(99)
        self.assertEqual((self.calls, task.done), ([], False))
        self.at(100)
        self.at(300)
        self.assertEqual(self.calls, ["a"])
        self.assertEqual(task.result, TaskResult(TaskStatus.FINISHED))

    def test_a_cancelled_delay_does_not_call_back(self) -> None:
        task = self.timer.after(delay_ms=100, callback=lambda: self.calls.append("a"))
        seen: list[TaskStatus] = []
        task.on_done(lambda result: seen.append(result.status))

        task.cancel()
        self.at(200)

        self.assertEqual((self.calls, seen), ([], [TaskStatus.CANCELLED]))

    def test_a_repeating_delay_goes_on_until_it_is_cancelled(self) -> None:
        task = self.timer.every(interval_ms=50, callback=lambda: self.calls.append("a"))

        for now in (50, 100, 150):
            self.at(now)
        self.assertEqual((len(self.calls), task.done), (3, False))

        self.timer.cancel(task)
        self.at(200)
        self.assertEqual(
            (len(self.calls), task.result), (3, TaskResult(TaskStatus.CANCELLED))
        )

    def test_cancelling_all_ends_every_delay(self) -> None:
        tasks = [
            self.timer.after(delay_ms=100, callback=lambda: self.calls.append("a")),
            self.timer.every(interval_ms=10, callback=lambda: self.calls.append("b")),
        ]

        self.timer.cancel_all()
        self.at(500)

        self.assertEqual(self.calls, [])
        self.assertTrue(all(task.done for task in tasks))

    def test_a_callback_may_start_the_next_delay(self) -> None:
        def again() -> None:
            self.calls.append("first")
            self.timer.after(delay_ms=10, callback=lambda: self.calls.append("second"))

        self.timer.after(delay_ms=10, callback=again)
        self.at(10)
        self.at(20)

        self.assertEqual(self.calls, ["first", "second"])


class TaskTests(unittest.TestCase):
    def test_a_callback_added_after_the_end_is_called_at_once(self) -> None:
        task = Task()
        task.complete(TaskResult(TaskStatus.FINISHED))
        task.complete(TaskResult(TaskStatus.CANCELLED))
        seen: list[TaskStatus] = []

        task.on_done(lambda result: seen.append(result.status))

        # The first end counts.
        self.assertEqual(seen, [TaskStatus.FINISHED])


if __name__ == "__main__":
    unittest.main()
