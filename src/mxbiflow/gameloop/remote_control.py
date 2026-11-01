"""Remote control of the game loop through cogmoteGO's command proxy.

The game loop registers the proxy ``mxbiflow`` with the commands of a
:class:`~mxbiflow.commands.CommandRegistry`: the built-in ones below, which
run the same actions as the keyboard shortcuts, and the experiment's own.
It polls them once per frame and replies with each command's result. See
``docs/remote-control.md``.
"""

import time
from collections.abc import Callable, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field, create_model
from pymotego import CommandDescription, CommandProxy, HandshakeError

from mxbiflow.driver.rewarder.rewarder import Rewarder

from ..commands import CommandRegistry, NoParams, RemoteCommand, Reply
from ..utils.logger import logger

#: Proxy name the game loop registers with cogmoteGO.
PROXY_NAME = "mxbiflow"

# Commands handled per frame, so a burst never stalls rendering.
_MAX_COMMANDS_PER_POLL = 10


class RemoteScheduler(Protocol):
    """Scheduler actions reachable from remote commands."""

    def level_up(self) -> None: ...

    def level_down(self) -> None: ...

    def next_stage(self) -> None: ...

    def prev_stage(self) -> None: ...

    def switch_stage(self, stage: str) -> None: ...

    def pause(self) -> None: ...

    def resume(self) -> None: ...


class RewardParams(BaseModel):
    duration_ms: int = Field(gt=0, le=10_000, title="Duration (ms)")


def builtin_commands(
    *,
    scheduler: RemoteScheduler,
    rewarder: Rewarder,
    on_capture: Callable[[], None],
    on_quit: Callable[[], None],
    stages: Sequence[str],
) -> list[RemoteCommand]:
    """mxbiflow's own commands; ``switch_stage`` offers the registered ``stages``."""

    def simple(
        name: str, title: str, action: Callable[[], None], **kwargs: bool | str
    ) -> RemoteCommand:
        return RemoteCommand(
            name=name,
            title=title,
            handler=lambda _params: action(),
            params=NoParams,
            **kwargs,  # pyright: ignore[reportArgumentType]
        )

    def reward(params: RewardParams) -> Reply:
        rewarder.give_reward(params.duration_ms)
        return Reply(message=f"gave a {params.duration_ms} ms reward")

    commands = [
        simple("level_up", "Level up", scheduler.level_up),
        simple("level_down", "Level down", scheduler.level_down),
        simple("next_stage", "Next stage", scheduler.next_stage),
        simple("prev_stage", "Previous stage", scheduler.prev_stage),
    ]
    if stages:
        switch_params = create_model(
            "SwitchStageParams",
            stage=(Literal[tuple(stages)], Field(title="Stage")),  # pyright: ignore[reportInvalidTypeForm, reportArgumentType]
        )
        commands.append(
            RemoteCommand(
                name="switch_stage",
                title="Switch stage",
                description="Move the current animal to a registered stage.",
                handler=lambda params: scheduler.switch_stage(params.stage),  # pyright: ignore[reportAttributeAccessIssue]
                params=switch_params,
            )
        )
    commands += [
        RemoteCommand(
            name="reward",
            title="Give reward",
            description="Manual reward on rewarder 0.",
            handler=reward,
            params=RewardParams,
        ),
        simple(
            "pause",
            "Pause",
            scheduler.pause,
            description="Show IDLE and start no task; a running trial is aborted.",
        ),
        simple("resume", "Resume", scheduler.resume),
        simple("screenshot", "Screenshot", on_capture),
        simple(
            "quit",
            "Quit",
            on_quit,
            description="End the run, as Esc does.",
            confirm=True,
        ),
    ]
    return commands


class RemoteControl:
    """Polls the ``mxbiflow`` command proxy and dispatches its commands.

    cogmoteGO may be missing or restart during a run: connecting is retried
    every ``retry_interval_s`` and the game loop never fails because of it.
    """

    def __init__(
        self,
        commands: CommandRegistry,
        *,
        connect: Callable[[Sequence[CommandDescription]], CommandProxy] = (
            lambda descriptions: CommandProxy(PROXY_NAME, descriptions)
        ),
        retry_interval_s: float = 5.0,
    ) -> None:
        self._commands = commands
        self._connect = connect
        self._retry_interval_s = retry_interval_s
        self._proxy: CommandProxy | None = None
        self._last_attempt: float | None = None

    def poll(self) -> None:
        """Run the commands that arrived since the last frame."""
        proxy = self._ensure_proxy()
        if proxy is None:
            return
        for _ in range(_MAX_COMMANDS_PER_POLL):
            command = proxy.get_command()
            if command is None:
                return
            reply = self._commands.dispatch(command.command, command.params)
            proxy.reply(command, reply.ok, reply.message, reply.data)

    def _ensure_proxy(self) -> CommandProxy | None:
        if self._proxy is not None:
            return self._proxy
        now = time.monotonic()
        if (
            self._last_attempt is not None
            and now - self._last_attempt < self._retry_interval_s
        ):
            return None
        first_attempt = self._last_attempt is None
        self._last_attempt = now
        try:
            self._proxy = self._connect(self._commands.describe())
        except (OSError, HandshakeError) as error:
            if first_attempt:
                logger.warning("command proxy unavailable, retrying: %s", error)
            return None
        logger.info("command proxy %s connected", PROXY_NAME)
        return self._proxy

    def close(self) -> None:
        """Close the proxy; cogmoteGO unregisters it."""
        if self._proxy is not None:
            self._proxy.close()
            self._proxy = None
