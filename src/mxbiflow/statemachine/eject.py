"""Turn an experiment file into Python that builds the same stages.

The code written is what one would write by hand with :mod:`~.stage`: every name an
enum member, a trial's parameters a model, and states, transitions and stimuli models
that refer to them; pictures and sounds become files beside it. It is for the
day a stage needs Python hooks; from then on the Python file is the experiment, since
hooks cannot go back into the file. cogforge's node positions (``layout``) are left out.

The source is a syntax tree printed by ``ast.unparse``, so it is valid Python whatever
the names and texts are.
"""

import ast
import importlib.util
import keyword
import mimetypes
import re
import subprocess
import sys
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from . import machine as machine_module
from .models import (
    After,
    Amount1,
    BackgroundStimulus,
    ClearAction,
    Duration,
    Experiment,
    HighAction,
    ImageStimulus,
    LowAction,
    ParamRef,
    Size,
    Stage,
    State,
    TextStimulus,
    TonesStimulus,
    WavStimulus,
)
from .runner import EXIT

ASSETS = "assets"
ANNOTATIONS = {"time": "Time", "count": "Count", "number": "float"}
# The models with more than one field take keywords only: their first fields' names.
FIELDS = {
    "State": ["name"],
    "Group": ["name"],
    "On": ["source", "event", "target"],
    "Timer": ["name", "time_ms"],
    "Counter": ["name", "event", "limit"],
    "SetHigh": ["output"],
    "SetLow": ["output"],
    "Background": ["name", "color"],
    "Image": ["name", "path"],
    "Rect": ["name"],
    "Circle": ["name"],
    "Cross": ["name"],
    "Text": ["name", "text"],
    "Tones": ["name", "tones", "duration_ms"],
    "Wav": ["name", "path"],
}
SUFFIXES = {
    "rise": "Rise",
    "fall": "Fall",
    "high": "High",
    "low": "Low",
    "reached": "Reached",
    "done": "Done",
    "touch": "Touch",
}


class _Names:
    """Python names for the format's names, unique in one scope."""

    def __init__(self, taken: Iterable[str], lead: str = "_") -> None:
        self._taken = set(taken)
        # What goes before a name that does not start as a Python name does.
        self._lead = lead

    def new(self, name: str) -> str:
        base = re.sub(r"\W", "_", name)
        if self._lead != "_":
            base = base.lstrip("_")
        if not base or base[0].isdigit():
            base = f"{self._lead}{base}"
        if keyword.iskeyword(base):
            base = f"{base}_"
        candidate, n = base, 1
        while candidate in self._taken:
            n += 1
            candidate = f"{base}_{n}"
        self._taken.add(candidate)
        return candidate


def _expr(value: Any) -> ast.expr:
    """A Python value as a syntax tree; whole floats are written as integers."""
    if isinstance(value, ast.expr):
        return value
    if isinstance(value, float) and value.is_integer():
        return ast.Constant(int(value))
    if isinstance(value, list):
        return ast.List([_expr(v) for v in value])  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, tuple):
        return ast.Tuple([_expr(v) for v in value])  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, dict):
        return ast.Dict(
            [_expr(k) for k in value],  # pyright: ignore[reportUnknownVariableType]
            [_expr(v) for v in value.values()],  # pyright: ignore[reportUnknownVariableType]
        )
    return ast.Constant(value)


def _call(function: str, *args: Any, **kwargs: Any) -> ast.Call:
    """``a.b(args, kwargs)``; a keyword whose value is ``None`` is left out."""
    first, *rest = function.split(".")
    target: ast.expr = ast.Name(first)
    for attribute in rest:
        target = ast.Attribute(target, attribute)
    return ast.Call(
        target,
        [_expr(a) for a in args],
        [ast.keyword(k, _expr(v)) for k, v in kwargs.items() if v is not None],
    )


def _media(data_url: str) -> tuple[str, bytes]:
    with urllib.request.urlopen(data_url) as response:
        return response.headers.get_content_type(), response.read()


class _Enum:
    """An enum of the format's names of one kind: its class and its members."""

    def __init__(self, name: str, values: Iterable[str]) -> None:
        self.name = name
        names = _Names([])
        self.members = {value: names.new(value).upper() for value in values}

    def __contains__(self, value: str) -> bool:
        return value in self.members

    def ref(self, value: str) -> ast.expr:
        return ast.Attribute(ast.Name(self.name), self.members[value])

    def definition(self) -> ast.ClassDef:
        """``class States(StrEnum)``; ``auto()`` where it gives the name."""
        body: list[ast.stmt] = [
            ast.Assign(
                [ast.Name(member, ast.Store())],
                _call("auto") if member.lower() == value else ast.Constant(value),
                lineno=0,
            )
            for value, member in self.members.items()
        ]
        return ast.ClassDef(self.name, [ast.Name("StrEnum")], [], body, [])


class _StageSource:
    """The enums, the parameters and the model of one stage."""

    def __init__(
        self,
        stage: Stage,
        prefix: str,
        variable: str,
        class_name: str,
        trial_class: str,
        files: dict[str, bytes],
    ) -> None:
        self.stage = stage
        self.variable = variable
        self.files = files
        self.used: set[str] = {"Machine", "State", "TrialParams"}
        self.class_name = class_name
        self.trial_class = trial_class
        self.machine = f"{variable.upper()}_MACHINE" if prefix else "MACHINE"
        machine = stage.machine
        hosts = [
            t.event.removeprefix("host.")
            for holder in (*machine.states, *machine.groups)
            for t in holder.transitions
            if t.event.startswith("host.")
        ]
        kinds: dict[str, Iterable[str]] = {
            "States": [s.name for s in machine.states],
            "Groups": [g.name for g in machine.groups],
            "Stimuli": [s.name for s in machine.stimuli],
            "Inputs": machine.channels.inputs,
            "Outputs": machine.channels.outputs,
            "Timers": [t.name for t in machine.timers],
            "Counters": [c.name for c in machine.counters],
            "HostEvents": hosts,
        }
        self.enums = {
            kind: _Enum(f"{prefix}{kind}", dict.fromkeys(values))
            for kind, values in kinds.items()
        }
        self.params_class = f"{prefix}Params"
        self.refs = f"{variable}_p" if prefix else "p"
        # A model's field cannot start with an underscore or be one of its methods.
        fields = _Names(dir(machine_module.TrialParams), lead="p")
        self.parameters = {p.name: fields.new(p.name) for p in machine.parameters}

    # ---- references ------------------------------------------------------------

    def _name(self, kind: str, value: str) -> ast.expr:
        return self.enums[kind].ref(value)

    def _param(self, name: str) -> ast.expr:
        return ast.Attribute(ast.Name(self.refs), self.parameters[name])

    def _amount(self, value: After | Amount1 | Duration | ParamRef) -> ast.expr:
        return (
            self._param(value.param)
            if isinstance(value, ParamRef)
            else _expr(value.root)
        )

    def _unless(self, value: Amount1 | ParamRef, default: float) -> ast.expr | None:
        if isinstance(value, Amount1) and value.root == default:
            return None
        return self._amount(value)

    def _of(self, kinds: Sequence[str], value: str | ParamRef, where: str) -> ast.expr:
        """A name of one of these kinds, or a parameter that names one."""
        if isinstance(value, ParamRef):
            return self._param(value.param)
        for kind in kinds:
            if value in self.enums[kind]:
                return self._name(kind, value)
        raise ValueError(
            f'stage "{self.stage.name}", {where}: nothing is named "{value}"'
        )

    def _target(self, value: str | ParamRef, where: str) -> ast.expr:
        if value == EXIT:
            self.used.add("EXIT")
            return ast.Name("EXIT")
        return self._of(["States"], value, where)

    def _model(self, name: str, *args: Any, **kwargs: Any) -> ast.Call:
        """A stage model's constructor: all keywords, but for a model of one field."""
        self.used.add(name)
        names = FIELDS.get(name)
        if names is None:
            return _call(name, *args, **kwargs)
        return _call(name, **dict(zip(names, args, strict=False)), **kwargs)

    def _event(self, event: str, where: str) -> ast.Call:
        if event == "screen.touch":
            return self._model("ScreenTouch")
        if event.startswith("host."):
            return self._model("Host", self._name("HostEvents", event[5:]))
        name, _, suffix = event.rpartition(".")
        kinds = {
            "reached": ["Counters"],
            "done": ["Timers", "Stimuli"],
            "touch": ["Stimuli"],
        }.get(suffix, ["Inputs"])
        if suffix not in SUFFIXES:
            raise ValueError(
                f'stage "{self.stage.name}", {where}: the event "{event}" is not known'
            )
        return self._model(SUFFIXES[suffix], self._of(kinds, name, where))

    def _file(self, stimulus: str, data_url: str) -> ast.expr:
        media, data = _media(data_url)
        extension = mimetypes.guess_extension(media)
        if extension is None:
            raise ValueError(
                f'stage "{self.stage.name}", stimulus "{stimulus}": '
                f"no file extension for {media}"
            )
        taken = _Names([Path(name).stem for name in self.files])
        name = taken.new(f"{self.variable}_{stimulus}") + extension
        self.files[name] = data
        return ast.BinOp(ast.Name("ASSETS"), ast.Div(), ast.Constant(name))

    # ---- the pieces -------------------------------------------------------------

    def _params(self) -> list[ast.stmt]:
        """``class Params(TrialParams)`` and ``p = Params.refs()``."""
        machine = self.stage.machine
        if not machine.parameters:
            return []
        self.used.add("TrialParams")
        body: list[ast.stmt] = []
        for parameter in machine.parameters:
            field = self.parameters[parameter.name]
            default: Any = parameter.default
            annotation: ast.expr
            if parameter.type == "state":
                default = self._target(parameter.default, parameter.name)
                # A parameter that starts at the exit is not one of the states' enum.
                of = "str" if parameter.default == EXIT else self.enums["States"].name
                annotation = self._marked("StateParam", of)
            elif parameter.type == "stimulus":
                default = self._of(["Stimuli"], parameter.default, parameter.name)
                annotation = self._marked("StimulusParam", self.enums["Stimuli"].name)
            else:
                name = ANNOTATIONS[parameter.type]
                if name != "float":
                    self.used.add(name)
                annotation = ast.Name(name)
            if field != parameter.name:
                default = _call("Field", default, alias=parameter.name)
            body.append(
                ast.AnnAssign(
                    ast.Name(field, ast.Store()),
                    annotation,
                    _expr(default),
                    simple=1,
                )
            )
        return [
            ast.ClassDef(self.params_class, [ast.Name("TrialParams")], [], body, []),
            ast.Assign(
                [ast.Name(self.refs, ast.Store())],
                _call(f"{self.params_class}.refs"),
                lineno=0,
            ),
        ]

    def _marked(self, marker: str, of: str) -> ast.expr:
        """``StateParam[States]``: what a parameter names, and from which enum."""
        self.used.add(marker)
        return ast.Subscript(ast.Name(marker), ast.Name(of))

    @property
    def needs_field(self) -> bool:
        return any(field != name for name, field in self.parameters.items())

    def _stimuli(self) -> list[ast.expr]:
        stimuli: list[ast.expr] = []
        for s in self.stage.machine.stimuli:
            name = self._name("Stimuli", s.name)
            if isinstance(s, BackgroundStimulus):
                stimuli.append(self._model("Background", name, s.color))
            elif isinstance(s, TonesStimulus):
                tones = [
                    (self._amount(t.frequency), self._amount(t.duration))
                    for t in s.tones
                ]
                stimuli.append(
                    self._model("Tones", name, tones, self._amount(s.duration))
                )
            elif isinstance(s, WavStimulus):
                path = None if s.sound is None else self._file(s.name, s.sound)
                stimuli.append(
                    self._model("Wav", name, _expr(path), duration_ms=s.duration)
                )
            else:
                first: list[Any] = [name]
                if isinstance(s, ImageStimulus):
                    first.append(
                        _expr(None if s.image is None else self._file(s.name, s.image))
                    )
                elif isinstance(s, TextStimulus):
                    first.append(s.text)
                size = None
                if s.size is not Size.fraction:
                    self.used.add("Size")
                    size = ast.Attribute(ast.Name("Size"), s.size.name)
                stimuli.append(
                    self._model(
                        s.kind.capitalize(),
                        *first,
                        x=self._amount(s.x),
                        y=self._amount(s.y),
                        width=s.width,
                        height=s.height,
                        color=None if isinstance(s, ImageStimulus) else s.color,
                        size=size,
                    )
                )
        return stimuli

    def _action(self, action: Any, where: str) -> ast.Call:
        if isinstance(action, ClearAction):
            return self._model("Clear")
        if isinstance(action, (HighAction, LowAction)):
            high = isinstance(action, HighAction)
            output = action.high if isinstance(action, HighAction) else action.low
            return self._model(
                "SetHigh" if high else "SetLow",
                self._name("Outputs", output),
                after_ms=None if action.after is None else self._amount(action.after),
            )
        ((kind, name),) = dict(action).items()
        kinds = {
            "show": ["Stimuli"],
            "hide": ["Stimuli"],
            "play": ["Stimuli"],
            "start": ["Timers"],
            "stop": ["Timers", "Stimuli"],
            "reset": ["Counters"],
            "cancel": ["Outputs"],
        }[kind]
        return self._model(kind.capitalize(), self._of(kinds, name, where))

    def _actions(self, actions: Iterable[Any], where: str) -> list[ast.Call] | None:
        return [self._action(action, where) for action in actions] or None

    def _state(self, state: State) -> ast.Call:
        outcome = self.stage.outcomes.get(state.name)
        if outcome is not None:
            self.used.add("Outcome")
        return self._model(
            "State",
            self._name("States", state.name),
            on_entry=self._actions(state.on_entry, state.name),
            on_exit=self._actions(state.on_exit, state.name),
            group=None if state.group is None else self._name("Groups", state.group),
            outcome=None
            if outcome is None
            else ast.Attribute(ast.Name("Outcome"), outcome.name),
        )

    def definitions(self, stage_name: ast.expr) -> list[ast.stmt]:
        """The stage's enums, its parameters, its machine and the stage's class."""
        machine = self.stage.machine
        body: list[ast.stmt] = [
            enum.definition() for enum in self.enums.values() if enum.members
        ]
        body += self._params()
        channels = {
            kind: ast.Name(self.enums[kind].name) if self.enums[kind].members else None
            for kind in ("Inputs", "Outputs")
        }
        transitions = [
            self._model(
                "On",
                self._of(["States", "Groups"], holder.name, holder.name),
                self._event(t.event, holder.name),
                target=None
                if t.target is None
                else self._target(t.target, holder.name),
                actions=self._actions(t.actions, holder.name),
            )
            for holder in (*machine.states, *machine.groups)
            for t in holder.transitions
        ]
        start = None
        if machine.states and machine.start != machine.states[0].name:
            start = self._name("States", machine.start)
        model = _call(
            "Machine",
            params=ast.Name(self.params_class) if machine.parameters else None,
            inputs=channels["Inputs"],
            outputs=channels["Outputs"],
            screen=(machine.screen.width, machine.screen.height),
            stimuli=self._stimuli() or None,
            timers=[
                self._model("Timer", self._name("Timers", t.name), self._amount(t.time))
                for t in machine.timers
            ]
            or None,
            counters=[
                self._model(
                    "Counter",
                    self._name("Counters", c.name),
                    self._event(c.event, c.name),
                    self._amount(c.limit),
                )
                for c in machine.counters
            ]
            or None,
            groups=[
                self._model(
                    "Group",
                    self._name("Groups", g.name),
                    on_entry=self._actions(g.on_entry, g.name),
                    on_exit=self._actions(g.on_exit, g.name),
                    parent=None if g.group is None else self._name("Groups", g.group),
                )
                for g in machine.groups
            ]
            or None,
            states=[self._state(state) for state in machine.states],
            start=start,
            transitions=transitions or None,
        )
        body.append(ast.Assign([ast.Name(self.machine, ast.Store())], model, lineno=0))
        body += self._stage_classes(stage_name)
        return body

    def _stage_classes(self, stage_name: ast.expr) -> list[ast.stmt]:
        """The stage's trial, and the stage giving each trial the defaults."""
        params = self.params_class if self.stage.machine.parameters else "TrialParams"

        def method(
            name: str, returns: str, value: ast.expr, *, of_class: bool = False
        ) -> ast.FunctionDef:
            return ast.FunctionDef(
                name,
                ast.arguments(args=[ast.arg("cls" if of_class else "self")]),
                [ast.Return(value)],
                [ast.Name("classmethod")] if of_class else [],
                ast.Name(returns),
            )

        return [
            ast.ClassDef(
                self.trial_class,
                [ast.Subscript(ast.Name("MachineTrial"), ast.Name(params))],
                [],
                [method("machine", "Machine", ast.Name(self.machine))],
                [],
            ),
            ast.ClassDef(
                self.class_name,
                [ast.Subscript(ast.Name("Stage"), ast.Name(params))],
                [],
                [
                    ast.Assign(
                        [ast.Name("trial", ast.Store())],
                        ast.Name(self.trial_class),
                        lineno=0,
                    ),
                    # The stage keeps the name it has in the file.
                    method("name", "str", stage_name, of_class=True),
                    method("next_trial", params, _call(params)),
                ],
                [],
            ),
        ]


def python_source(experiment: Experiment, origin: str) -> tuple[str, dict[str, bytes]]:
    """The Python source that builds ``experiment``, and its picture and sound files.

    The files are by name, and the source expects them in the directory ``assets``
    beside it. ``origin`` names what the source was written from, for its docstring.
    """
    files: dict[str, bytes] = {}
    several = len(experiment.stages) > 1
    taken = [
        "scenes",
        "ASSETS",
        "Path",
        "p",
        "MachineTrial",
        "Stage",
        *machine_module.__all__,
    ]
    variables = _Names(taken)
    classes = _Names(taken)
    stage_names = _Enum("Stages", [stage.name for stage in experiment.stages])
    stages: list[_StageSource] = []
    for stage in experiment.stages:
        variable = variables.new(stage.name)
        prefix = "".join(part.capitalize() for part in variable.split("_"))
        class_name = classes.new(prefix or "Stage")
        stages.append(
            _StageSource(
                stage,
                prefix if several else "",
                variable,
                class_name,
                classes.new(f"{class_name}Trial"),
                files,
            )
        )
    definitions: list[ast.stmt] = [stage_names.definition()]
    for stage in stages:
        definitions += stage.definitions(stage_names.ref(stage.stage.name))
    used = sorted(set[str]().union(*(stage.used for stage in stages)))
    body: list[ast.stmt] = [
        ast.Expr(
            ast.Constant(
                f"Written by `mxbiflow eject` from {origin}.\n\n"
                "Register `scenes` with the scene manager. A stage's `next_trial` "
                "gives each\ntrial its values; its `decide` reads the trial's record "
                "and moves the animal\nbetween levels.\n"
            )
        ),
        ast.ImportFrom("enum", [ast.alias("StrEnum"), ast.alias("auto")], 0),
        ast.ImportFrom(
            "mxbiflow.statemachine.machine", [ast.alias(name) for name in used], 0
        ),
        ast.ImportFrom("mxbiflow.statemachine.scene", [ast.alias("MachineTrial")], 0),
        ast.ImportFrom("mxbiflow.statemachine.stage", [ast.alias("Stage")], 0),
    ]
    if any(stage.needs_field for stage in stages):
        body.append(ast.ImportFrom("pydantic", [ast.alias("Field")], 0))
    if files:
        body.insert(2, ast.ImportFrom("pathlib", [ast.alias("Path")], 0))
        parent = ast.Attribute(_call("Path", ast.Name("__file__")), "parent")
        body.append(
            ast.Assign(
                [ast.Name("ASSETS", ast.Store())],
                ast.BinOp(parent, ast.Div(), ast.Constant(ASSETS)),
                lineno=0,
            )
        )
    body += definitions
    body.append(
        ast.Assign(
            [ast.Name("scenes", ast.Store())],
            ast.List([_call(f"{stage.class_name}.scene") for stage in stages]),
            lineno=0,
        )
    )
    return ast.unparse(ast.fix_missing_locations(ast.Module(body))) + "\n", files


def eject(
    experiment: Experiment, directory: Path, origin: str, *, name: str = "stages.py"
) -> Path:
    """Write the Python source of ``experiment`` and its files into ``directory``.

    Refuses to write over an existing source file: it may hold hand-written hooks.
    The source is formatted with ruff when ruff is installed.
    """
    target = directory / name
    if target.exists():
        raise FileExistsError(f"{target} exists; it is not written over")
    source, files = python_source(experiment, origin)
    directory.mkdir(parents=True, exist_ok=True)
    if files:
        (directory / ASSETS).mkdir(exist_ok=True)
    for file, data in files.items():
        (directory / ASSETS / file).write_bytes(data)
    target.write_text(source, encoding="utf-8")
    if importlib.util.find_spec("ruff") is not None:
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--quiet", str(target)], check=True
        )
    return target
