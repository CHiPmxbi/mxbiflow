"""Remote commands described with pydantic and run from cogmote.

Each command has a name, a title for its button, an optional description,
whether to confirm, and a params model. The registry describes every command
in the command proxy's hello (``model_json_schema()`` for the params), so
cogmote renders the controls, and validates and dispatches the commands it
receives through a discriminated union. mxbiflow's built-in commands and an
experiment's own are registered the same way. See ``docs/remote-control.md``.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    create_model,
)
from pymotego import CommandDescription

from .utils.logger import logger


class NoParams(BaseModel):
    """Params of a command that takes none."""

    model_config = ConfigDict(extra="forbid")


class Reply(BaseModel):
    """What a command returns to cogmote: ``{ok, message?, data?}``."""

    ok: bool = True
    message: str | None = None
    data: JsonValue = None


type Handler[P: BaseModel] = Callable[[P], Reply | None]


@dataclass(frozen=True)
class RemoteCommand[P: BaseModel]:
    """A command and its handler, which gets the validated params.

    A handler returning ``None`` replies ``ok``; one that raises replies
    ``ok: false`` with the error, and the run goes on.
    """

    name: str
    title: str
    handler: Handler[P]
    params: type[P]
    description: str | None = None
    confirm: bool = False

    def describe(self) -> CommandDescription:
        return CommandDescription.from_model(
            self.name,
            self.params if self.params.model_fields else None,
            title=self.title,
            description=self.description,
            confirm=self.confirm,
        )


class CommandRegistry:
    """Commands by name; names are unique."""

    def __init__(self, commands: Iterable[RemoteCommand[Any]] = ()) -> None:
        self._commands: dict[str, RemoteCommand[Any]] = {}
        self._adapter: TypeAdapter[Any] | None = None
        for command in commands:
            self.register(command)

    @property
    def commands(self) -> list[RemoteCommand[Any]]:
        return list(self._commands.values())

    def register(self, command: RemoteCommand[Any]) -> None:
        if command.name in self._commands:
            raise ValueError(f"command {command.name!r} is already registered")
        self._commands[command.name] = command
        self._adapter = None

    def command[P: BaseModel](
        self,
        name: str,
        *,
        title: str,
        params: type[P] = NoParams,
        description: str | None = None,
        confirm: bool = False,
    ) -> Callable[[Handler[P]], Handler[P]]:
        """Register the decorated function as the handler of command ``name``."""

        def decorate(handler: Handler[P]) -> Handler[P]:
            self.register(
                RemoteCommand(
                    name=name,
                    title=title,
                    handler=handler,
                    params=params,
                    description=description,
                    confirm=confirm,
                )
            )
            return handler

        return decorate

    def describe(self) -> list[CommandDescription]:
        return [command.describe() for command in self._commands.values()]

    def dispatch(self, command: str, params: dict[str, JsonValue]) -> Reply:
        """Validate and run one command; never raises."""
        if not self._commands:
            return Reply(ok=False, message=f"unknown command {command!r}")
        try:
            request = self._union().validate_python(
                {"command": command, "params": params}
            )
        except ValidationError as error:
            logger.warning("remote command rejected: %s %s (%s)", command, params, error)
            return Reply(ok=False, message=_reason(error))

        logger.info("remote command: %s %s", command, params)
        try:
            reply = self._commands[command].handler(request.params)
        except Exception as error:  # noqa: BLE001 - a remote command never ends the run
            logger.exception("remote command failed: %s", command)
            return Reply(ok=False, message=str(error) or type(error).__name__)
        return reply if reply is not None else Reply()

    def _union(self) -> TypeAdapter[Any]:
        """Discriminated union of ``{command: <name>, params: <model>}``."""
        if self._adapter is None:
            models: list[type[BaseModel]] = [
                create_model(
                    f"Command_{command.name}",
                    command=(Literal[command.name], ...),  # pyright: ignore[reportInvalidTypeForm, reportArgumentType]
                    params=(command.params, ...),
                )
                for command in self._commands.values()
            ]
            union = Union[tuple(models)]  # noqa: UP007 - built at runtime  # pyright: ignore[reportInvalidTypeArguments]
            self._adapter = TypeAdapter(
                Annotated[union, Field(discriminator="command")]  # pyright: ignore[reportInvalidTypeForm, reportArgumentType]
            )
        return self._adapter


def _reason(error: ValidationError) -> str:
    """One line per failure, without the union's model names."""
    reasons: list[str] = []
    for item in error.errors(include_url=False):
        # loc is (<command>, "params", <field>...) inside the union; keep the field path.
        loc = [str(part) for part in item["loc"][2:]]
        prefix = ".".join(loc) + ": " if loc else ""
        if item["type"] == "union_tag_invalid":
            return "unknown command"
        reasons.append(prefix + item["msg"])
    return "; ".join(reasons)
