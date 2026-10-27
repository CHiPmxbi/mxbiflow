import unittest

from pydantic import JsonValue

from mxbiflow.gameloop.remote_control import RemoteControl


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def level_up(self) -> None:
        self.calls.append("level_up")

    def level_down(self) -> None:
        self.calls.append("level_down")

    def next_stage(self) -> None:
        self.calls.append("next_stage")

    def prev_stage(self) -> None:
        self.calls.append("prev_stage")

    def switch_stage(self, stage: str) -> None:
        self.calls.append(f"switch_stage:{stage}")

    def pause(self) -> None:
        self.calls.append("pause")

    def resume(self) -> None:
        self.calls.append("resume")


class FakeRewarder:
    def __init__(self) -> None:
        self.rewards: list[int] = []

    def open(self) -> None:
        pass

    def give_reward(self, duration_ms: int) -> None:
        self.rewards.append(duration_ms)

    def give_reward_by_volume(self, volume_ul: int) -> None:
        pass

    def give_reward_by_count(self, count: int) -> None:
        pass

    def stop_reward(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeProxy:
    def __init__(self, commands: list[JsonValue]) -> None:
        self.commands = commands
        self.closed = False

    def get_command(self, timeout: float = 0) -> JsonValue | None:
        return self.commands.pop(0) if self.commands else None

    def close(self) -> None:
        self.closed = True


class RemoteControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = FakeScheduler()
        self.rewarder = FakeRewarder()
        self.events: list[str] = []
        self.proxy = FakeProxy([])
        self.connects = 0

    def _connect(self) -> FakeProxy:
        self.connects += 1
        return self.proxy

    def _remote(self, **kwargs: object) -> RemoteControl:
        return RemoteControl(
            scheduler=self.scheduler,
            rewarder=self.rewarder,
            on_capture=lambda: self.events.append("screenshot"),
            on_quit=lambda send_report: self.events.append(f"quit:{send_report}"),
            connect=self._connect,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )

    def test_dispatches_every_command(self) -> None:
        self.proxy.commands = [
            {"command": "level_up"},
            {"command": "level_down"},
            {"command": "next_stage"},
            {"command": "prev_stage"},
            {"command": "switch_stage", "stage": "detect"},
            {"command": "pause"},
            {"command": "resume"},
            {"command": "reward", "duration_ms": 300},
            {"command": "screenshot"},
            {"command": "quit", "send_report": False},
        ]
        remote = self._remote()

        remote.poll()

        self.assertEqual(
            self.scheduler.calls,
            [
                "level_up",
                "level_down",
                "next_stage",
                "prev_stage",
                "switch_stage:detect",
                "pause",
                "resume",
            ],
        )
        self.assertEqual(self.rewarder.rewards, [300])
        self.assertEqual(self.events, ["screenshot", "quit:False"])

    def test_quit_without_a_report_choice(self) -> None:
        self.proxy.commands.append({"command": "quit"})

        self._remote().poll()

        self.assertEqual(self.events, ["quit:None"])

    def test_invalid_commands_are_ignored(self) -> None:
        remote = self._remote()

        for body in [
            None,
            "level_up",
            {"command": "explode"},
            {"command": "switch_stage"},
            {"command": "reward", "duration_ms": 0},
            {"command": "reward", "duration_ms": 60_000},
        ]:
            remote.dispatch(body)

        self.assertEqual(self.scheduler.calls, [])
        self.assertEqual(self.rewarder.rewards, [])

    def test_failing_command_does_not_raise(self) -> None:
        def broken() -> None:
            raise RuntimeError("boom")

        self.scheduler.level_up = broken  # type: ignore[method-assign]
        remote = self._remote()

        remote.dispatch({"command": "level_up"})
        remote.dispatch({"command": "level_down"})

        self.assertEqual(self.scheduler.calls, ["level_down"])

    def test_poll_handles_a_bounded_burst(self) -> None:
        burst: list[JsonValue] = [{"command": "level_up"} for _ in range(25)]
        self.proxy.commands = burst
        remote = self._remote()

        remote.poll()

        self.assertEqual(len(self.scheduler.calls), 10)

    def test_retries_connecting_after_the_interval(self) -> None:
        attempts: list[int] = []

        def refuse() -> FakeProxy:
            attempts.append(1)
            raise ConnectionRefusedError("cogmoteGO is not running")

        remote = RemoteControl(
            scheduler=self.scheduler,
            rewarder=self.rewarder,
            on_capture=lambda: None,
            on_quit=lambda _send_report: None,
            connect=refuse,  # type: ignore[arg-type]
            retry_interval_s=0.0,
        )
        remote.poll()
        remote.poll()
        self.assertEqual(len(attempts), 2)

        slow = RemoteControl(
            scheduler=self.scheduler,
            rewarder=self.rewarder,
            on_capture=lambda: None,
            on_quit=lambda _send_report: None,
            connect=refuse,  # type: ignore[arg-type]
            retry_interval_s=60.0,
        )
        slow.poll()
        slow.poll()
        self.assertEqual(len(attempts), 3)

    def test_close_closes_the_proxy(self) -> None:
        remote = self._remote()
        remote.poll()

        remote.close()

        self.assertTrue(self.proxy.closed)
        self.assertEqual(self.connects, 1)


if __name__ == "__main__":
    unittest.main()
