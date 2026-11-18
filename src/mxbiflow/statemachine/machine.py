"""Write a trial's state machine in Python: names as enums, the rest as models.

A :class:`Machine` is the same data cogforge exports for a stage, written so that the
editor and the type checker see every reference: a name is an enum member, the trial's
parameters are the fields of a :class:`TrialParams` model, and states, transitions and
stimuli are models that refer to each other by those. A name is any string, so a plain
``str`` works wherever an enum member does.

    class S(StrEnum):
        WAIT = auto()
        GIVE = auto()

    class Out(StrEnum):
        REWARD = auto()

    class Stim(StrEnum):
        TARGET = auto()

    class Params(TrialParams):
        reward_ms: Time = 500

    p = Params.refs()

    MACHINE = Machine(
        params=Params,
        outputs=Out,
        stimuli=[
            Rect(name=Stim.TARGET, x=0.5, y=0.3, width=0.3, height=0.3, color="#ffffff")
        ],
        states=[
            State(name=S.WAIT, timeout_ms=5000, on_entry=[Show(Stim.TARGET)]),
            State(
                name=S.GIVE,
                timeout_ms=p.reward_ms,
                hold=[Out.REWARD],
                on_entry=[Clear()],
                outcome=Outcome.correct,
            ),
        ],
        transitions=[
            On(source=S.WAIT, event=Touch(Stim.TARGET), target=S.GIVE),
            On(source=S.WAIT, event=Timeout(), target=EXIT),
            On(source=S.GIVE, event=Timeout(), target=EXIT),
        ],
    )

A model with more than one field takes keyword arguments only, so each argument says
what it is; an action or an event of one field (``Show(Stim.TARGET)``) may go without.

The machine is only the trial. Which values a trial gets, and what its outcome does to
the animal's level, is the stage's own Python: :class:`~.scene.MachineTrial`.
"""

import base64
import mimetypes
from collections.abc import Iterable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Self, TypeVar, cast

import soundfile
from pydantic import (
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
)
from pydantic.dataclasses import dataclass
from pydantic_core import core_schema

from .models import Outcomes as Outcome
from .models import Size
from .models import Stage as StageData
from .runner import EXIT
from .validate import machine_problems

__all__ = [
    "EXIT",
    "Background",
    "Circle",
    "Clear",
    "Count",
    "Counter",
    "Cross",
    "Done",
    "Fall",
    "Generator",
    "Group",
    "Hide",
    "High",
    "Host",
    "Image",
    "Low",
    "Machine",
    "On",
    "Outcome",
    "Play",
    "Reached",
    "Rect",
    "Ref",
    "Reset",
    "Rise",
    "ScreenTouch",
    "Show",
    "Size",
    "Start",
    "State",
    "StateParam",
    "StimulusParam",
    "Stop",
    "Text",
    "Time",
    "Timeout",
    "Timer",
    "Tones",
    "Touch",
    "TrialParams",
    "Wav",
]

_CONFIG = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


# ---- parameters ---------------------------------------------------------------


class Ref(str):
    """A parameter, where a value could stand: its value is the trial's.

    It is the parameter's name, so it is also the key of the parameter in a level's
    values and in ``scene.values``. Take one from ``Params.refs()``.
    """

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.is_instance_schema(cls)


class _Kind:
    def __init__(self, kind: str) -> None:
        self.kind = kind


#: A parameter that is a time in milliseconds; drawn from a range it is a whole number.
Time = Annotated[float, _Kind("time")]
#: A parameter that is a whole number of something.
Count = Annotated[int, _Kind("count")]
_N = TypeVar("_N", bound=str)
#: A parameter that names where a transition leads: ``StateParam[S]`` for the states'
#: enum ``S``, ``StateParam[str]`` for plain names.
StateParam = Annotated[_N, _Kind("state")]
#: A parameter that names the stimulus to show or play: ``StimulusParam[Stim]``.
StimulusParam = Annotated[_N, _Kind("stimulus")]

type Amount = float | Ref
type Name = str
type StimulusName = Name | Ref


class TrialParams(BaseModel):
    """A trial's parameters: subclass it with a field for each.

    The field's type says what the parameter is: :data:`Time`, :data:`Count`, ``float``
    for any other number, :data:`StateParam` for where a transition leads and
    :data:`StimulusParam` for which stimulus to show or play. A field of any other
    type is refused. Its default is the parameter's.
    A field's alias is the parameter's name when that is not a Python name. An instance
    is the values of one trial, which a stage gives its machine.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @classmethod
    def refs(cls) -> Self:
        """The parameters themselves, to put where a state or a stimulus takes one.

        ``Params.refs().reward_ms`` is the parameter ``reward_ms``, not a number; the
        type checker reads it as the field, so a misspelt name is an error.
        """
        return cast(Self, _Refs(cls))


class _Refs:
    def __init__(self, params: type[TrialParams]) -> None:
        self._params = params

    def __getattr__(self, name: str) -> Ref:
        field = self._params.model_fields.get(name)
        if field is None:
            raise AttributeError(f"{self._params.__name__} has no parameter {name}")
        return Ref(field.alias or name)


# ---- what a state does when it is entered ------------------------------------


@dataclass(frozen=True, config=_CONFIG)
class Show:
    """Show a visual stimulus, on top of what is shown."""

    stimulus: StimulusName


@dataclass(frozen=True, config=_CONFIG)
class Hide:
    stimulus: StimulusName


@dataclass(frozen=True, config=_CONFIG)
class Clear:
    """Clear the screen."""


@dataclass(frozen=True, config=_CONFIG)
class Play:
    """Play a sound; when it has played to its end the event is :class:`Done`."""

    sound: StimulusName


@dataclass(frozen=True, config=_CONFIG)
class Start:
    """Start a timer or a pulse generator."""

    name: Name


@dataclass(frozen=True, config=_CONFIG)
class Stop:
    """Stop a timer, a pulse generator or a sound."""

    name: StimulusName


@dataclass(frozen=True, config=_CONFIG)
class Reset:
    counter: Name


type Action = Show | Hide | Clear | Play | Start | Stop | Reset

_ACTIONS: dict[type, str] = {
    Show: "show",
    Hide: "hide",
    Play: "play",
    Stop: "stop",
    Start: "start",
    Reset: "reset",
}


# ---- events -------------------------------------------------------------------


@dataclass(frozen=True, config=_CONFIG)
class Timeout:
    """The state's ``timeout_ms`` ran out."""


@dataclass(frozen=True, config=_CONFIG)
class Touch:
    """The animal touched this stimulus.

    An event is a stimulus's, not a parameter's: for a stimulus a parameter names, give
    each stimulus it can name its own transition.
    """

    stimulus: Name


@dataclass(frozen=True, config=_CONFIG)
class ScreenTouch:
    """The animal touched the screen where no stimulus is."""


@dataclass(frozen=True, config=_CONFIG)
class Done:
    """A timer or a pulse generator is done, or a sound has played to its end."""

    name: Name


@dataclass(frozen=True, config=_CONFIG)
class Reached:
    """A counter reached its limit."""

    counter: Name


@dataclass(frozen=True, config=_CONFIG)
class Rise:
    input: Name


@dataclass(frozen=True, config=_CONFIG)
class Fall:
    input: Name


@dataclass(frozen=True, config=_CONFIG)
class High:
    """The input is high, also when the state is entered with it high."""

    input: Name


@dataclass(frozen=True, config=_CONFIG)
class Low:
    input: Name


@dataclass(frozen=True, config=_CONFIG)
class Host:
    """An event the stage's Python sends with ``scene.fire(name)``."""

    name: Name


type Event = (
    Timeout | Touch | ScreenTouch | Done | Reached | Rise | Fall | High | Low | Host
)


# ---- the machine --------------------------------------------------------------


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class State:
    """A state; the first one of a stage is where a trial starts.

    ``hold`` are outputs high while the machine is in the state. When ``timeout_ms`` runs
    out the event is :class:`Timeout`. A trial's outcome is that of the last state
    entered that has one.
    """

    name: Name
    timeout_ms: Amount | None = None
    hold: Sequence[Name] = ()
    on_entry: Sequence[Action] = ()
    group: Name | None = None
    outcome: Outcome | None = None


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Group:
    """A group of states: its hold and its transitions apply in each of them."""

    name: Name
    hold: Sequence[Name] = ()
    parent: Name | None = None


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class On:
    """In state or group ``source``, ``event`` leads to ``target``.

    A state's transitions are tried in the order given, before its groups'. The target
    is a state, :data:`EXIT` (the trial ends) or a parameter that names a state.
    """

    source: Name
    event: Event
    target: Name | Ref


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Timer:
    """A time that runs across states; the event is :class:`Done`."""

    name: Name
    time_ms: Amount


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Counter:
    """Counts an event; at the limit the event is :class:`Reached`."""

    name: Name
    event: Event
    limit: Amount


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Generator:
    """A pulse or a pulse train on an output; ``count`` 0 runs until stopped."""

    name: Name
    output: Name
    width_ms: Amount
    delay_ms: Amount = 0
    period_ms: Amount = 0
    count: Amount = 1


# ---- stimuli ------------------------------------------------------------------


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Background:
    name: Name
    color: str


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class _Placed:
    """Where a visual stimulus is: its centre as fractions of the animal's screen.

    A ``fraction`` size is of the screen's width, for the width and the height.
    """

    x: Amount
    y: Amount
    width: float
    height: float
    size: Size = Size.fraction


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Image(_Placed):
    """A picture; ``None`` shows a frame with the stimulus's name."""

    name: Name
    path: Path | None


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Rect(_Placed):
    name: Name
    color: str


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Circle(_Placed):
    name: Name
    color: str


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Cross(_Placed):
    name: Name
    color: str


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Text(_Placed):
    name: Name
    text: str
    color: str


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Tones:
    """Tones as ``(frequency in Hz, duration in ms)``, repeated for ``duration_ms``.

    Frequency 0 is silence. Each may be a parameter, drawn per trial.
    """

    name: Name
    tones: Sequence[tuple[Amount, Amount]]
    duration_ms: Amount


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Wav:
    """A sound file; its length is read from the file unless ``duration_ms`` is given.

    ``None`` is silence that lasts ``duration_ms``.
    """

    name: Name
    path: Path | None
    duration_ms: float | None = None


type Stimulus = Background | Image | Rect | Circle | Cross | Text | Tones | Wav

# ---- the machine as a whole ---------------------------------------------------


def _names(names: Iterable[str]) -> list[str]:
    """Plain strings of names, which may be an enum class or its members."""
    return [str(name) for name in names]


def _amount(value: Amount | str) -> Any:
    return {"param": str(value)} if isinstance(value, Ref) else value


def _data_url(path: Path, kind: str) -> str:
    media = mimetypes.guess_type(path.name)[0]
    if media is None or not media.startswith(f"{kind}/"):
        raise ValueError(f"{path} is not an {kind} file")
    return f"data:{media};base64,{base64.b64encode(path.read_bytes()).decode()}"


@dataclass(frozen=True, config=_CONFIG, kw_only=True)
class Machine:
    """A trial as a state machine: what a stage's trial does, as data.

    Times are milliseconds. ``inputs`` and ``outputs`` are the channels the machine
    uses, wired by the rig. ``screen`` is the layout's reference and says whether it is
    upright; stimuli are placed by fractions of the rig's screen. The trial's values
    are the stage's to give (:class:`~.scene.MachineTrial`); ``defaults`` are what the
    format keeps for a parameter a trial leaves out.
    """

    states: Sequence[State]
    transitions: Sequence[On] = ()
    params: type[TrialParams] = TrialParams
    #: The parameters' defaults, when they are not the fields' own.
    defaults: TrialParams | None = None
    #: Names, or the enum class of them.
    inputs: Sequence[Name] | type[StrEnum] = ()
    outputs: Sequence[Name] | type[StrEnum] = ()
    screen: tuple[int, int] = (1080, 1920)
    stimuli: Sequence[Stimulus] = ()
    timers: Sequence[Timer] = ()
    generators: Sequence[Generator] = ()
    counters: Sequence[Counter] = ()
    groups: Sequence[Group] = ()
    start: Name | None = None

    def _parameters(self) -> list[dict[str, Any]]:
        parameters: list[dict[str, Any]] = []
        if self.defaults is not None and not isinstance(self.defaults, self.params):
            raise ValueError(f"the defaults are not a {self.params.__name__}")
        for field_name, field in self.params.model_fields.items():
            name = field.alias or field_name
            kinds = [m.kind for m in field.metadata if isinstance(m, _Kind)]
            if self.defaults is not None:
                default = getattr(self.defaults, field_name)
            elif field.is_required():
                raise ValueError(f"parameter {name} needs a default")
            else:
                default = field.default
            if kinds:
                kind = kinds[0]
            elif field.annotation is float:
                kind = "number"
            else:
                raise ValueError(
                    f"parameter {name}: its type does not say what it is; use Time, "
                    "Count, float, StateParam[...] or StimulusParam[...]"
                )
            if isinstance(default, str):
                default = str(default)
            parameters.append({"name": name, "type": kind, "default": default})
        return parameters

    def _action(self, action: Action) -> dict[str, Any]:
        if isinstance(action, Clear):
            return {"clear": True}
        (value,) = (getattr(action, f) for f in action.__dataclass_fields__)
        return {_ACTIONS[type(action)]: _amount(value)}

    def _stimulus(self, stimulus: Stimulus) -> dict[str, Any]:
        name = str(stimulus.name)
        match stimulus:
            case Background():
                return {"kind": "background", "name": name, "color": stimulus.color}
            case Tones():
                return {
                    "kind": "tones",
                    "name": name,
                    "tones": [
                        {"frequency": _amount(f), "duration": _amount(d)}
                        for f, d in stimulus.tones
                    ],
                    "duration": _amount(stimulus.duration_ms),
                }
            case Wav():
                duration = stimulus.duration_ms
                if duration is None:
                    if stimulus.path is None:
                        raise ValueError(
                            f'sound "{name}" has no file: give its duration_ms'
                        )
                    info = soundfile.info(str(stimulus.path))
                    duration = round(info.frames / info.samplerate * 1000)
                sound = (
                    None if stimulus.path is None else _data_url(stimulus.path, "audio")
                )
                return {
                    "kind": "wav",
                    "name": name,
                    "sound": sound,
                    "duration": duration,
                }
            case _:
                placed: dict[str, Any] = {
                    "kind": type(stimulus).__name__.lower(),
                    "name": name,
                    "x": _amount(stimulus.x),
                    "y": _amount(stimulus.y),
                    "size": stimulus.size,
                    "width": stimulus.width,
                    "height": stimulus.height,
                }
                if isinstance(stimulus, Image):
                    path = stimulus.path
                    placed["image"] = None if path is None else _data_url(path, "image")
                else:
                    placed["color"] = stimulus.color
                if isinstance(stimulus, Text):
                    placed["text"] = stimulus.text
                return placed

    def build(self, name: str) -> StageData:
        """The machine as the format's stage called ``name``; raises for a wrong name."""
        transitions: dict[str, list[dict[str, Any]]] = {}
        for on in self.transitions:
            target = (
                _amount(on.target) if isinstance(on.target, Ref) else str(on.target)
            )
            transitions.setdefault(str(on.source), []).append(
                {"event": _event(on.event), "target": target}
            )
        holders = _names(s.name for s in (*self.states, *self.groups))
        problems = [
            f'a transition from "{source}", which is no state or group'
            for source in transitions
            if source not in holders
        ]
        data: dict[str, Any] = {
            "name": name,
            "machine": {
                "channels": {
                    "inputs": _names(self.inputs),
                    "outputs": _names(self.outputs),
                },
                "parameters": self._parameters(),
                "timers": [
                    {"name": str(t.name), "time": _amount(t.time_ms)}
                    for t in self.timers
                ],
                "generators": [
                    {
                        "name": str(g.name),
                        "output": str(g.output),
                        "delay": _amount(g.delay_ms),
                        "width": _amount(g.width_ms),
                        "period": _amount(g.period_ms),
                        "count": _amount(g.count),
                    }
                    for g in self.generators
                ],
                "counters": [
                    {
                        "name": str(c.name),
                        "event": _event(c.event),
                        "limit": _amount(c.limit),
                    }
                    for c in self.counters
                ],
                "start": str(
                    self.start or (self.states[0].name if self.states else "")
                ),
                "groups": [
                    {
                        "name": str(g.name),
                        "group": None if g.parent is None else str(g.parent),
                        "hold": _names(g.hold),
                        "transitions": transitions.get(str(g.name), []),
                    }
                    for g in self.groups
                ],
                "states": [
                    {
                        "name": str(s.name),
                        "group": None if s.group is None else str(s.group),
                        "hold": _names(s.hold),
                        "timeout": None
                        if s.timeout_ms is None
                        else _amount(s.timeout_ms),
                        "onEntry": [self._action(a) for a in s.on_entry],
                        "transitions": transitions.get(str(s.name), []),
                    }
                    for s in self.states
                ],
                "layout": {},
                "screen": {"width": self.screen[0], "height": self.screen[1]},
                "stimuli": [self._stimulus(s) for s in self.stimuli],
            },
            "outcomes": {
                str(s.name): s.outcome for s in self.states if s.outcome is not None
            },
        }
        problems += _dangling(data)
        if problems:
            raise ValueError(f'stage "{name}": ' + "; ".join(problems))
        stage = StageData.model_validate(data)
        problems = machine_problems(stage.machine)
        if problems:
            raise ValueError(f'stage "{name}": ' + "; ".join(problems))
        return stage


def _event(event: Event) -> str:
    """The format's name of an event."""
    match event:
        case Timeout():
            return "timeout"
        case ScreenTouch():
            return "screen.touch"
        case Touch(stimulus=stimulus):
            return f"{stimulus}.touch"
        case Done(name=name):
            return f"{name}.done"
        case Reached(counter=counter):
            return f"{counter}.reached"
        case Rise(input=name):
            return f"{name}.rise"
        case Fall(input=name):
            return f"{name}.fall"
        case High(input=name):
            return f"{name}.high"
        case Low(input=name):
            return f"{name}.low"
        case Host(name=name):
            return f"host.{name}"


def _dangling(data: dict[str, Any]) -> list[str]:
    """Names that lead nowhere would fail silently in a trial: say where they are."""
    machine = data["machine"]
    problems: list[str] = []
    states = {s["name"] for s in machine["states"]}
    groups = {g["name"] for g in machine["groups"]}
    if len(states) != len(machine["states"]) or states & groups or EXIT in states:
        problems.append("a state's or a group's name is used twice")
    if machine["start"] not in states:
        problems.append(f'the start state "{machine["start"]}" does not exist')
    targets = {p["name"] for p in machine["parameters"] if p["type"] == "state"}
    startable = {t["name"] for t in machine["timers"] + machine["generators"]}
    counters = {c["name"] for c in machine["counters"]}
    kinds = {s["name"]: s["kind"] for s in machine["stimuli"]}
    if len(kinds) != len(machine["stimuli"]):
        problems.append("a stimulus's name is used twice")
    sounds = {name for name, kind in kinds.items() if kind in ("wav", "tones")}
    visuals = set(kinds) - sounds
    known: dict[str, set[str]] = {
        "show": visuals,
        "hide": visuals,
        "play": sounds,
        "start": startable,
        "stop": startable | sounds,
        "reset": counters,
    }
    for holder in (*machine["states"], *machine["groups"]):
        where = holder["name"]
        if holder["group"] is not None and holder["group"] not in groups:
            problems.append(f'{where}: no group "{holder["group"]}"')
        for output in holder["hold"]:
            if output not in machine["channels"]["outputs"]:
                problems.append(f'{where}: no output "{output}"')
        events = [transition["event"] for transition in holder["transitions"]]
        for event in dict.fromkeys(events):
            if events.count(event) > 1:
                # The first would always win, whatever the second was meant for.
                problems.append(f'{where}: "{event}" has more than one transition')
        for transition in holder["transitions"]:
            target = transition["target"]
            if isinstance(target, dict):
                if target["param"] not in targets:
                    problems.append(f'{where}: no state parameter "{target["param"]}"')
            elif target != EXIT and target not in states:
                problems.append(f'{where}: no state "{target}"')
        for action in holder.get("onEntry", []):
            ((kind, name),) = action.items()
            # What a stimulus parameter names is checked with the trial's values.
            if kind in known and not isinstance(name, dict) and name not in known[kind]:
                problems.append(f'{where}: {kind} "{name}" does not exist')
    for generator in machine["generators"]:
        if generator["output"] not in machine["channels"]["outputs"]:
            problems.append(f'{generator["name"]}: no output "{generator["output"]}"')
    return problems
