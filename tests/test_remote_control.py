import unittest
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, JsonValue
from pymotego import Command, CommandDescription

from mxbiflow.commands import CommandRegistry, Reply
from mxbiflow.gameloop.remote_control import RemoteControl, builtin_commands


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
    def __init__(self) -> None:
        self.commands: list[Command] = []
        self.replies: list[tuple[str, bool, str | None, JsonValue]] = []
        self.descriptions: Sequence[CommandDescription] = ()
        self.closed = False

    def push(self, command: str, **params: JsonValue) -> None:
        self.commands.append(
            Command(
                id=str(len(self.commands)),
                command=command,
                params=params,
                expires_at=datetime.now(UTC) + timedelta(seconds=5),
            )
        )

    def get_command(self, timeout: float = 0) -> Command | None:
        return self.commands.pop(0) if self.commands else None

    def reply(
        self,
        command: Command,
        ok: bool,
        message: str | None = None,
        data: JsonValue = None,
    ) -> None:
        self.replies.append((command.command, ok, message, data))

    def close(self) -> None:
        self.closed = True


class Hint(BaseModel):
    side: str = Field(pattern="^(left|right)$")


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CommandRegistry()
        self.hints: list[str] = []

        @self.registry.command(
            "show_hint", title="Show hint", params=Hint, confirm=True
        )
        def show_hint(params: Hint) -> Reply:
            self.hints.append(params.side)
            return Reply(message=f"hint on the {params.side}", data={"n": 1})

        @self.registry.command("noop", title="No-op")
        def noop(_params: object) -> None:
            pass

    def test_describes_commands(self) -> None:
        descriptions = [
            d.model_dump(mode="json", exclude_none=True)
            for d in self.registry.describe()
        ]
        self.assertEqual(
            descriptions,
            [
                {
                    "name": "show_hint",
                    "title": "Show hint",
                    "params": Hint.model_json_schema(),
                    "confirm": True,
                },
                {"name": "noop", "title": "No-op", "confirm": False},
            ],
        )

    def test_dispatches_validated_params(self) -> None:
        reply = self.registry.dispatch("show_hint", {"side": "left"})
        self.assertEqual(reply, Reply(message="hint on the left", data={"n": 1}))
        self.assertEqual(self.hints, ["left"])
        self.assertEqual(self.registry.dispatch("noop", {}), Reply())

    def test_rejects_invalid_commands(self) -> None:
        for command, params in [
            ("explode", {}),
            ("show_hint", {}),
            ("show_hint", {"side": "up"}),
            ("noop", {"x": 1}),
        ]:
            reply = self.registry.dispatch(command, params)
            self.assertFalse(reply.ok, (command, params))
            self.assertTrue(reply.message)
        self.assertEqual(self.registry.dispatch("explode", {}).message, "unknown command")
        self.assertIn("side", self.registry.dispatch("show_hint", {}).message or "")
        self.assertEqual(self.hints, [])

    def test_duplicate_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.command("noop", title="Again")(lambda _params: None)

    def test_failing_handler_replies_not_ok(self) -> None:
        @self.registry.command("broken", title="Broken")
        def broken(_params: object) -> None:
            raise RuntimeError("boom")

        self.assertEqual(self.registry.dispatch("broken", {}), Reply(ok=False, message="boom"))


class RemoteControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = FakeScheduler()
        self.rewarder = FakeRewarder()
        self.events: list[str] = []
        self.proxy = FakeProxy()
        self.connects = 0

    def _connect(self, descriptions: Sequence[CommandDescription]) -> FakeProxy:
        self.connects += 1
        self.proxy.descriptions = descriptions
        return self.proxy

    def _registry(self) -> CommandRegistry:
        return CommandRegistry(
            builtin_commands(
                scheduler=self.scheduler,
                rewarder=self.rewarder,  # type: ignore[arg-type]
                on_capture=lambda: self.events.append("screenshot"),
                on_quit=lambda: self.events.append("quit"),
                stages=["detect", "train"],
            )
        )

    def _remote(self, **kwargs: object) -> RemoteControl:
        return RemoteControl(
            self._registry(),
            connect=self._connect,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )

    def test_describes_builtin_commands(self) -> None:
        self._remote().poll()
        by_name = {d.name: d for d in self.proxy.descriptions}
        self.assertEqual(
            list(by_name),
            [
                "level_up",
                "level_down",
                "next_stage",
                "prev_stage",
                "switch_stage",
                "reward",
                "pause",
                "resume",
                "screenshot",
                "quit",
            ],
        )
        self.assertIsNone(by_name["pause"].params)
        self.assertTrue(by_name["quit"].confirm)
        stage = (by_name["switch_stage"].params or {})["properties"]
        self.assertEqual(stage["stage"]["enum"], ["detect", "train"])  # type: ignore[index]
        self.assertEqual(
            (by_name["reward"].params or {})["required"], ["duration_ms"]
        )

    def test_dispatches_every_command(self) -> None:
        for name in ["level_up", "level_down", "next_stage", "prev_stage"]:
            self.proxy.push(name)
        self.proxy.push("switch_stage", stage="detect")
        self.proxy.push("pause")
        self.proxy.push("resume")
        self.proxy.push("reward", duration_ms=300)
        self.proxy.push("screenshot")
        self.proxy.push("quit")
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
        self.assertEqual(self.events, ["screenshot", "quit"])
        self.assertTrue(all(ok for _, ok, _, _ in self.proxy.replies))
        self.assertIn(("reward", True, "gave a 300 ms reward", None), self.proxy.replies)

    def test_invalid_commands_reply_not_ok(self) -> None:
        self.proxy.push("explode")
        self.proxy.push("switch_stage")
        self.proxy.push("switch_stage", stage="unknown")
        self.proxy.push("reward", duration_ms=0)
        self.proxy.push("reward", duration_ms=60_000)
        self._remote().poll()

        self.assertEqual(len(self.proxy.replies), 5)
        self.assertFalse(any(ok for _, ok, _, _ in self.proxy.replies))
        self.assertEqual(self.scheduler.calls, [])
        self.assertEqual(self.rewarder.rewards, [])

    def test_failing_command_does_not_raise(self) -> None:
        def broken() -> None:
            raise RuntimeError("boom")

        self.scheduler.level_up = broken  # type: ignore[method-assign]
        self.proxy.push("level_up")
        self.proxy.push("level_down")
        self._remote().poll()

        self.assertEqual(self.scheduler.calls, ["level_down"])
        self.assertEqual(self.proxy.replies[0], ("level_up", False, "boom", None))

    def test_poll_handles_a_bounded_burst(self) -> None:
        for _ in range(25):
            self.proxy.push("level_up")
        self._remote().poll()

        self.assertEqual(len(self.scheduler.calls), 10)

    def test_retries_connecting_after_the_interval(self) -> None:
        attempts: list[int] = []

        def refuse(_descriptions: Sequence[CommandDescription]) -> FakeProxy:
            attempts.append(1)
            raise ConnectionRefusedError("cogmoteGO is not running")

        remote = RemoteControl(
            self._registry(),
            connect=refuse,  # type: ignore[arg-type]
            retry_interval_s=0.0,
        )
        remote.poll()
        remote.poll()
        self.assertEqual(len(attempts), 2)

        slow = RemoteControl(
            self._registry(),
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
