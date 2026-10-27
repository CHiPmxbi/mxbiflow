"""Remote control of the game loop through cogmoteGO's command proxy.

cogmote and agents send commands to ``POST /proxies/mxbiflow/requests`` on
cogmoteGO; the game loop polls them once per frame and runs the same actions
as the keyboard shortcuts. See ``docs/remote-control.md``.
"""

import time
from collections.abc import Callable
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, Field, JsonValue, TypeAdapter, ValidationError
from pymotego import CommandProxy, HandshakeError

from mxbiflow.driver.rewarder.rewarder import Rewarder

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


class _SimpleCommand(BaseModel):
    command: Literal[
        "level_up",
        "level_down",
        "next_stage",
        "prev_stage",
        "pause",
        "resume",
        "screenshot",
        "quit",
    ]


class _SwitchStage(BaseModel):
    command: Literal["switch_stage"]
    stage: str = Field(min_length=1)


class _Reward(BaseModel):
    command: Literal["reward"]
    duration_ms: int = Field(gt=0, le=10_000)


type Command = Annotated[
    _SimpleCommand | _SwitchStage | _Reward, Field(discriminator="command")
]

# pydantic resolves `type` aliases; its stubs do not accept them yet.
_command_adapter: TypeAdapter[Command] = TypeAdapter(Command)  # pyright: ignore[reportArgumentType]


def parse_command(body: JsonValue) -> Command:
    """Validate a command body; raises ``ValidationError`` when it is invalid."""
    return _command_adapter.validate_python(body)


class RemoteControl:
    """Polls the ``mxbiflow`` command proxy and dispatches its commands.

    cogmoteGO may be missing or restart during a run: connecting is retried
    every ``retry_interval_s`` and the game loop never fails because of it.
    """

    def __init__(
        self,
        *,
        scheduler: RemoteScheduler,
        rewarder: Rewarder,
        on_capture: Callable[[], None],
        on_quit: Callable[[], None],
        connect: Callable[[], CommandProxy] = lambda: CommandProxy(PROXY_NAME),
        retry_interval_s: float = 5.0,
    ) -> None:
        self._scheduler = scheduler
        self._rewarder = rewarder
        self._on_capture = on_capture
        self._on_quit = on_quit
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
            body = proxy.get_command()
            if body is None:
                return
            self.dispatch(body)

    def dispatch(self, body: JsonValue) -> None:
        """Run one command body; invalid or failing commands are logged."""
        try:
            command = parse_command(body)
        except ValidationError as error:
            logger.warning("remote command rejected: %s (%s)", body, error)
            return

        logger.info("remote command: %s", body)
        try:
            self._run(command)
        except Exception:  # noqa: BLE001 - a remote command never ends the run
            logger.exception("remote command failed: %s", body)

    def _run(self, command: Command) -> None:
        match command:
            case _SwitchStage(stage=stage):
                self._scheduler.switch_stage(stage)
            case _Reward(duration_ms=duration_ms):
                self._rewarder.give_reward(duration_ms)
            case _SimpleCommand(command="level_up"):
                self._scheduler.level_up()
            case _SimpleCommand(command="level_down"):
                self._scheduler.level_down()
            case _SimpleCommand(command="next_stage"):
                self._scheduler.next_stage()
            case _SimpleCommand(command="prev_stage"):
                self._scheduler.prev_stage()
            case _SimpleCommand(command="pause"):
                self._scheduler.pause()
            case _SimpleCommand(command="resume"):
                self._scheduler.resume()
            case _SimpleCommand(command="screenshot"):
                self._on_capture()
            case _SimpleCommand(command="quit"):
                self._on_quit()

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
            self._proxy = self._connect()
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
