"""Turn an experiment file into Python that builds the same stages.

The code written is what one would write by hand with :class:`~.builder.StageBuilder`:
one function per stage, pictures and sounds as files beside it. It is for the day a
stage needs Python hooks; from then on the Python file is the experiment, since hooks
cannot go back into the file. cogforge's node positions (``layout``) are left out.

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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import builder
from .models import (
    Amount1,
    BackgroundStimulus,
    ClearAction,
    CountProgression,
    Duration,
    Experiment,
    Generator,
    ImageStimulus,
    Level,
    Order,
    ParamRef,
    RateProgression,
    Size,
    Stage,
    State,
    TextStimulus,
    TonesStimulus,
    Transition,
    Value1,
    Value2,
    WavStimulus,
)
from .runner import EXIT

ASSETS = "assets"
PARAMETERS = {
    "time": "add_time",
    "count": "add_count",
    "number": "add_number",
    "state": "add_target",
    "stimulus": "add_stimulus_parameter",
}


class _Names:
    """Python names for the format's names, unique in one scope."""

    def __init__(self, taken: Sequence[str]) -> None:
        self._taken = set(taken)

    def new(self, name: str) -> str:
        base = re.sub(r"\W", "_", name)
        if not base or base[0].isdigit():
            base = f"_{base}"
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


class _StageSource:
    """The function that builds one stage."""

    def __init__(self, stage: Stage, function: str, files: dict[str, bytes]) -> None:
        self.stage = stage
        self.function = function
        self.files = files
        self.used: set[str] = {"StageBuilder"}
        names = _Names(["stage", "ASSETS", "Path", *builder.__all__])
        machine = stage.machine
        self.parameters = {p.name: names.new(p.name) for p in machine.parameters}
        self.stimuli = {s.name: names.new(s.name) for s in machine.stimuli}

    def _amount(self, value: Amount1 | Duration | ParamRef) -> ast.expr:
        if isinstance(value, ParamRef):
            return ast.Name(self.parameters[value.param])
        return _expr(value.root)

    def _unless(self, value: Amount1 | ParamRef, default: float) -> ast.expr | None:
        if isinstance(value, Amount1) and value.root == default:
            return None
        return self._amount(value)

    def _stimulus(self, name: str | ParamRef) -> ast.expr:
        if isinstance(name, ParamRef):
            return ast.Name(self.parameters[name.param])
        return ast.Name(self.stimuli[name]) if name in self.stimuli else _expr(name)

    def _event(self, event: str) -> ast.expr:
        """``f"{target}.touch"`` for a stimulus's event, so a rename is one edit."""
        name, _, suffix = event.rpartition(".")
        if name in self.stimuli and suffix in ("touch", "done"):
            return ast.JoinedStr(
                [
                    ast.FormattedValue(ast.Name(self.stimuli[name]), -1),
                    ast.Constant(f".{suffix}"),
                ]
            )
        return _expr(event)

    def _file(self, stimulus: str, data_url: str) -> ast.expr:
        media, data = _media(data_url)
        extension = mimetypes.guess_extension(media)
        if extension is None:
            raise ValueError(
                f'stage "{self.stage.name}", stimulus "{stimulus}": '
                f"no file extension for {media}"
            )
        taken = _Names([Path(name).stem for name in self.files])
        name = taken.new(f"{self.function}_{stimulus}") + extension
        self.files[name] = data
        return ast.BinOp(ast.Name("ASSETS"), ast.Div(), ast.Constant(name))

    def _assign(self, variable: str, call: ast.Call) -> ast.stmt:
        return ast.Assign([ast.Name(variable, ast.Store())], call, lineno=0)

    def _parameters(self) -> list[ast.stmt]:
        return [
            self._assign(
                self.parameters[p.name],
                _call(f"stage.{PARAMETERS[p.type]}", p.name, p.default),
            )
            for p in self.stage.machine.parameters
        ]

    def _stimuli(self) -> list[ast.stmt]:
        body: list[ast.stmt] = []
        for s in self.stage.machine.stimuli:
            if isinstance(s, BackgroundStimulus):
                call = _call("stage.add_background", s.name, s.color)
            elif isinstance(s, TonesStimulus):
                tones = [
                    (self._amount(t.frequency), self._amount(t.duration))
                    for t in s.tones
                ]
                call = _call("stage.add_tones", s.name, tones, self._amount(s.duration))
            elif isinstance(s, WavStimulus):
                path = None if s.sound is None else self._file(s.name, s.sound)
                call = _call(
                    "stage.add_wav", s.name, _expr(path), duration_ms=s.duration
                )
            else:
                where: dict[str, Any] = {
                    "x": self._amount(s.x),
                    "y": self._amount(s.y),
                    "width": s.width,
                    "height": s.height,
                    "color": None if isinstance(s, ImageStimulus) else s.color,
                    "size": None if s.size is Size.fraction else s.size.value,
                }
                first: list[Any] = [s.name]
                if isinstance(s, ImageStimulus):
                    first.append(
                        _expr(None if s.image is None else self._file(s.name, s.image))
                    )
                elif isinstance(s, TextStimulus):
                    first.append(s.text)
                call = _call(f"stage.add_{s.kind}", *first, **where)
            body.append(self._assign(self.stimuli[s.name], call))
        return body

    def _action(self, action: Any) -> ast.Call:
        if isinstance(action, ClearAction):
            self.used.add("clear")
            return _call("clear")
        ((kind, name),) = dict(action).items()
        self.used.add(kind)
        return _call(kind, self._stimulus(name))

    def _state(self, state: State) -> ast.stmt:
        call = _call(
            "stage.add_state",
            state.name,
            hold=state.hold or None,
            timeout=None if state.timeout is None else self._amount(state.timeout),
            on_entry=[self._action(a) for a in state.on_entry] or None,
            group=state.group,
        )
        return ast.Expr(call)

    def _transition(self, source: str, transition: Transition) -> ast.stmt:
        target: ast.expr
        if isinstance(transition.target, ParamRef):
            target = ast.Name(self.parameters[transition.target.param])
        elif transition.target == EXIT:
            self.used.add("EXIT")
            target = ast.Name("EXIT")
        else:
            target = _expr(transition.target)
        return ast.Expr(
            _call("stage.add_transition", source, self._event(transition.event), target)
        )

    def _generator(self, g: Generator) -> ast.stmt:
        return ast.Expr(
            _call(
                "stage.add_generator",
                g.name,
                g.output,
                width=self._amount(g.width),
                delay=self._unless(g.delay, 0),
                period=self._unless(g.period, 0),
                count=self._unless(g.count, 1),
            )
        )

    def _level(self, level: Level) -> list[ast.stmt]:
        values = {
            name: value.uniform
            if isinstance(value, Value1)
            else value.choice
            if isinstance(value, Value2)
            else value
            for name, value in level.values.items()
        }
        body: list[ast.stmt] = [
            ast.Expr(
                _call("stage.add_level", level.name, *([values] if values else []))
            )
        ]
        for factor in level.factors:
            weights = {row.name: row.weight for row in factor.rows if row.weight != 1}
            body.append(
                ast.Expr(
                    _call(
                        "stage.add_factor",
                        level.name,
                        factor.name,
                        {row.name: row.values for row in factor.rows},
                        weights=weights or None,
                        order=None
                        if factor.order is Order.random
                        else factor.order.value,
                    )
                )
            )
        return body

    def _rule(self) -> list[ast.stmt]:
        rule = self.stage.progression
        if isinstance(rule, RateProgression):
            call = _call(
                "stage.set_rate_rule",
                min_trials=rule.min_trials,
                up=rule.up,
                down=rule.down,
            )
        elif isinstance(rule, CountProgression):
            call = _call("stage.set_count_rule", rule.correct)
        else:
            return []
        return [ast.Expr(call)]

    def definition(self) -> ast.FunctionDef:
        stage, machine = self.stage, self.stage.machine
        screen = (machine.screen.width, machine.screen.height)
        body: list[ast.stmt] = [
            self._assign(
                "stage",
                _call(
                    "StageBuilder",
                    stage.name,
                    inputs=machine.channels.inputs or None,
                    outputs=machine.channels.outputs or None,
                    screen=screen,
                ),
            )
        ]
        body += self._parameters()
        body += self._stimuli()
        body += [
            ast.Expr(_call("stage.add_timer", t.name, self._amount(t.time)))
            for t in machine.timers
        ]
        body += [self._generator(g) for g in machine.generators]
        body += [
            ast.Expr(_call("stage.add_counter", c.name, c.event, self._amount(c.limit)))
            for c in machine.counters
        ]
        body += [
            ast.Expr(
                _call("stage.add_group", g.name, hold=g.hold or None, parent=g.group)
            )
            for g in machine.groups
        ]
        body += [self._state(state) for state in machine.states]
        if machine.states and machine.start != machine.states[0].name:
            body.append(ast.Expr(_call("stage.set_start", machine.start)))
        for holder in (*machine.states, *machine.groups):
            body += [self._transition(holder.name, t) for t in holder.transitions]
        body += [
            ast.Expr(_call("stage.set_outcome", state, outcome.value))
            for state, outcome in stage.outcomes.items()
        ]
        for level in stage.levels:
            body += self._level(level)
        body += self._rule()
        body.append(ast.Return(ast.Name("stage")))
        return ast.FunctionDef(
            self.function,
            ast.arguments(),
            body,
            returns=ast.Name("StageBuilder"),
            lineno=0,
        )


def python_source(experiment: Experiment, origin: str) -> tuple[str, dict[str, bytes]]:
    """The Python source that builds ``experiment``, and its picture and sound files.

    The files are by name, and the source expects them in the directory ``assets``
    beside it. ``origin`` names what the source was written from, for its docstring.
    """
    files: dict[str, bytes] = {}
    functions = _Names(["scenes", "ASSETS", "Path", *builder.__all__])
    stages = [
        _StageSource(stage, functions.new(stage.name), files)
        for stage in experiment.stages
    ]
    definitions = [stage.definition() for stage in stages]
    used = sorted({"stage_scenes"}.union(*(stage.used for stage in stages)))
    animal_values = {a.name: a.values for a in experiment.animals if a.values}
    body: list[ast.stmt] = [
        ast.Expr(
            ast.Constant(
                f"Written by `mxbiflow eject` from {origin}.\n\n"
                "Register `scenes` with the scene manager. Add Python hooks to a stage "
                "with\n`stage.on_trial(hook)` and `stage.on_enter(state, hook)` before "
                "it is returned.\n"
            )
        ),
        ast.ImportFrom(
            "mxbiflow.statemachine.builder", [ast.alias(name) for name in used], 0
        ),
    ]
    if files:
        body.insert(1, ast.ImportFrom("pathlib", [ast.alias("Path")], 0))
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
            _call(
                "stage_scenes",
                *(_call(stage.function) for stage in stages),
                animal_values=animal_values or None,
            ),
            lineno=0,
        )
    )
    return ast.unparse(ast.Module(body)) + "\n", files


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
