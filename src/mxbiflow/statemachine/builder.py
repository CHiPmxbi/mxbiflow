"""Write a stage's state machine in Python, without cogforge.

:class:`StageBuilder` has the classic interface: add states, add transitions on events,
add timers, counters and stimuli, by name. It builds the same :class:`~.models.Stage`
that cogforge exports, so the machine stays data that the runner executes and that
could be opened in cogforge or loaded into rt-core. What data cannot say goes into
hooks: Python functions the host calls before a trial and when a state is entered.

    stage = StageBuilder("touch", outputs=["reward"])
    target = stage.add_rect("target", x=0.5, y=0.3, width=0.3, height=0.3, color="#ffffff")
    stage.add_state("wait", on_entry=[show(target)], timeout=5000)
    stage.add_state("give", hold=["reward"], on_entry=[clear()], timeout=500)
    stage.add_transition("wait", f"{target}.touch", "give")
    stage.add_transition("wait", "timeout", EXIT)
    stage.add_transition("give", "timeout", EXIT)
    stage.set_outcome("give", "correct")

    scene_manager.register(stage_scenes(stage))
"""

import base64
import mimetypes
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import soundfile

from ..scene.scene import Scene
from .models import Experiment, ParamRef, Stage
from .runner import EXIT
from .scene import Hook, Hooks, machine_scenes

__all__ = [
    "EXIT",
    "StageBuilder",
    "clear",
    "hide",
    "play",
    "reset",
    "show",
    "stage_scenes",
    "start",
    "stop",
]

type Amount = float | ParamRef
type Action = dict[str, Any]
type SizeUnit = Literal["px", "fraction"]
type Fixed = float | str


# ---- what a state does when it is entered ------------------------------------


def show(stimulus: str) -> Action:
    """Show a visual stimulus, on top of what is shown."""
    return {"show": stimulus}


def hide(stimulus: str) -> Action:
    return {"hide": stimulus}


def clear() -> Action:
    """Clear the screen."""
    return {"clear": True}


def play(sound: str) -> Action:
    """Play a sound; when it has played to its end the event is ``<sound>.done``."""
    return {"play": sound}


def start(name: str) -> Action:
    """Start a timer or a pulse generator."""
    return {"start": name}


def stop(name: str) -> Action:
    """Stop a timer, a pulse generator or a sound."""
    return {"stop": name}


def reset(counter: str) -> Action:
    return {"reset": counter}


def _amount(value: Amount | str) -> Any:
    return {"param": value.param} if isinstance(value, ParamRef) else value


def _data_url(path: Path, kind: str) -> str:
    media = mimetypes.guess_type(path.name)[0]
    if media is None or not media.startswith(f"{kind}/"):
        raise ValueError(f"{path} is not an {kind} file")
    return f"data:{media};base64,{base64.b64encode(path.read_bytes()).decode()}"


class StageBuilder:
    """One stage: a trial state machine, its levels, outcomes and Python hooks.

    Everything is referred to by name. Times are milliseconds. A time, a count or a
    transition's target may be a parameter (``add_time``, ``add_count``,
    ``add_target``, ``add_number``), which a level, a trial type or an ``on_trial``
    hook sets per trial. ``screen`` is the layout's reference and says whether it is
    upright; stimuli are placed by fractions of the rig's screen.
    """

    def __init__(
        self,
        name: str,
        *,
        inputs: Sequence[str] = (),
        outputs: Sequence[str] = (),
        screen: tuple[int, int] = (1080, 1920),
    ) -> None:
        self.name = name
        self._inputs = list(inputs)
        self._outputs = list(outputs)
        self._screen = screen
        self._parameters: list[dict[str, Any]] = []
        self._timers: list[dict[str, Any]] = []
        self._generators: list[dict[str, Any]] = []
        self._counters: list[dict[str, Any]] = []
        self._groups: dict[str, dict[str, Any]] = {}
        self._states: dict[str, dict[str, Any]] = {}
        self._stimuli: dict[str, dict[str, Any]] = {}
        self._start: str | None = None
        self._outcomes: dict[str, str] = {}
        self._levels: list[dict[str, Any]] = []
        self._progression: dict[str, Any] = {"rule": "manual"}
        self._hooks = Hooks()

    # ---- parameters ----------------------------------------------------------

    def _parameter(self, name: str, kind: str, default: Fixed) -> ParamRef:
        self._parameters.append({"name": name, "type": kind, "default": default})
        return ParamRef(param=name)

    def add_time(self, name: str, default_ms: float) -> ParamRef:
        """A time in milliseconds that a trial may set."""
        return self._parameter(name, "time", default_ms)

    def add_count(self, name: str, default: int) -> ParamRef:
        return self._parameter(name, "count", default)

    def add_number(self, name: str, default: float) -> ParamRef:
        """Any other number, such as a stimulus position."""
        return self._parameter(name, "number", default)

    def add_target(self, name: str, default_state: str) -> ParamRef:
        """A state to go to that a trial may set, such as where the left choice leads."""
        return self._parameter(name, "state", default_state)

    # ---- stimuli -------------------------------------------------------------

    def _stimulus(self, name: str, kind: str, **fields: Any) -> str:
        if name in self._stimuli:
            raise ValueError(f'stimulus "{name}" is added twice')
        self._stimuli[name] = {"kind": kind, "name": name, **fields}
        return name

    def _visual(
        self,
        name: str,
        kind: str,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        size: SizeUnit,
        **fields: Any,
    ) -> str:
        return self._stimulus(
            name,
            kind,
            x=_amount(x),
            y=_amount(y),
            size=size,
            width=width,
            height=height,
            **fields,
        )

    def add_image(
        self,
        name: str,
        path: Path | None,
        *,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        size: SizeUnit = "fraction",
    ) -> str:
        """A picture; ``None`` shows a frame with the stimulus's name."""
        image = _data_url(path, "image") if path is not None else None
        return self._visual(name, "image", x, y, width, height, size, image=image)

    def add_rect(
        self,
        name: str,
        *,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        color: str,
        size: SizeUnit = "fraction",
    ) -> str:
        return self._visual(name, "rect", x, y, width, height, size, color=color)

    def add_circle(
        self,
        name: str,
        *,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        color: str,
        size: SizeUnit = "fraction",
    ) -> str:
        return self._visual(name, "circle", x, y, width, height, size, color=color)

    def add_cross(
        self,
        name: str,
        *,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        color: str,
        size: SizeUnit = "fraction",
    ) -> str:
        return self._visual(name, "cross", x, y, width, height, size, color=color)

    def add_text(
        self,
        name: str,
        text: str,
        *,
        x: Amount,
        y: Amount,
        width: float,
        height: float,
        color: str,
        size: SizeUnit = "fraction",
    ) -> str:
        return self._visual(
            name, "text", x, y, width, height, size, color=color, text=text
        )

    def add_background(self, name: str, color: str) -> str:
        return self._stimulus(name, "background", color=color)

    def add_tones(
        self, name: str, tones: Sequence[tuple[float, float]], duration_ms: float
    ) -> str:
        """Tones as ``(frequency in Hz, duration in ms)``, repeated for ``duration_ms``.

        Frequency 0 is silence.
        """
        return self._stimulus(
            name,
            "tones",
            tones=[{"frequency": f, "duration": d} for f, d in tones],
            duration=duration_ms,
        )

    def add_wav(
        self, name: str, path: Path | None, *, duration_ms: float | None = None
    ) -> str:
        """A sound file; its length is read from the file unless ``duration_ms`` is given.

        ``None`` is silence that lasts ``duration_ms``.
        """
        if duration_ms is None:
            if path is None:
                raise ValueError(f'sound "{name}" has no file: give its duration_ms')
            info = soundfile.info(str(path))
            duration_ms = round(info.frames / info.samplerate * 1000)
        sound = _data_url(path, "audio") if path is not None else None
        return self._stimulus(name, "wav", sound=sound, duration=duration_ms)

    # ---- the machine ---------------------------------------------------------

    def add_state(
        self,
        name: str,
        *,
        hold: Sequence[str] = (),
        timeout: Amount | None = None,
        on_entry: Sequence[Action] = (),
        group: str | None = None,
    ) -> str:
        """A state; the first one added is where a trial starts.

        ``hold`` are outputs high while the machine is in the state. When ``timeout``
        runs out the event is ``timeout``.
        """
        if name in self._states or name in self._groups or name == EXIT:
            raise ValueError(f'"{name}" is already a state or a group')
        self._states[name] = {
            "name": name,
            "group": group,
            "hold": list(hold),
            "timeout": None if timeout is None else _amount(timeout),
            "onEntry": list(on_entry),
            "transitions": [],
        }
        if self._start is None:
            self._start = name
        return name

    def add_group(
        self, name: str, *, hold: Sequence[str] = (), parent: str | None = None
    ) -> str:
        """A group of states: its hold and transitions apply in each of them."""
        if name in self._states or name in self._groups or name == EXIT:
            raise ValueError(f'"{name}" is already a state or a group')
        self._groups[name] = {
            "name": name,
            "group": parent,
            "hold": list(hold),
            "transitions": [],
        }
        return name

    def add_transition(self, source: str, event: str, target: str | ParamRef) -> None:
        """In state or group ``source``, ``event`` leads to ``target``.

        A state's transitions are tried in the order added, before its groups'. The
        target is a state, :data:`EXIT` (the trial ends) or an ``add_target``
        parameter. Events: ``<input>.rise/fall/high/low``, ``timeout``,
        ``<timer>.done``, ``<generator>.done``, ``<sound>.done``,
        ``<counter>.reached``, ``<stimulus>.touch``, ``screen.touch`` and
        ``host.<name>`` (sent with ``scene.fire(name)``).
        """
        holder = self._states.get(source) or self._groups.get(source)
        if holder is None:
            raise ValueError(f'no state or group "{source}"')
        holder["transitions"].append({"event": event, "target": _amount(target)})

    def set_start(self, state: str) -> None:
        self._start = state

    def add_timer(self, name: str, time: Amount) -> str:
        """A time that runs across states; the event is ``<name>.done``."""
        self._timers.append({"name": name, "time": _amount(time)})
        return name

    def add_counter(self, name: str, event: str, limit: Amount) -> str:
        """Counts an event; at the limit the event is ``<name>.reached``."""
        self._counters.append({"name": name, "event": event, "limit": _amount(limit)})
        return name

    def add_generator(
        self,
        name: str,
        output: str,
        *,
        width: Amount,
        delay: Amount = 0,
        period: Amount = 0,
        count: Amount = 1,
    ) -> str:
        """A pulse or pulse train on an output; ``count`` 0 runs until stopped."""
        self._generators.append(
            {
                "name": name,
                "output": output,
                "delay": _amount(delay),
                "width": _amount(width),
                "period": _amount(period),
                "count": _amount(count),
            }
        )
        return name

    # ---- outcomes, levels, level rule ----------------------------------------

    def set_outcome(
        self, state: str, outcome: Literal["correct", "incorrect", "miss"]
    ) -> None:
        """A trial's outcome is that of the last state entered that has one."""
        self._outcomes[state] = outcome

    def add_level(
        self,
        name: str,
        values: Mapping[str, Fixed | tuple[float, float]] | None = None,
        *,
        types: Mapping[str, Mapping[str, Fixed]] | None = None,
        weights: Mapping[str, float] | None = None,
        order: Literal["random", "cycle"] = "random",
    ) -> None:
        """A level's parameter values; a ``(low, high)`` pair is drawn per trial.

        ``types`` are kinds of trial, by name: values that go together, one kind drawn
        per trial (or taken in turn with ``order="cycle"``). A kind is drawn as often
        as its weight in ``weights`` says, 1 unless given.
        """
        unknown = set(weights or {}) - set(types or {})
        if unknown:
            raise ValueError(f'level "{name}": weights for no type: {sorted(unknown)}')
        self._levels.append(
            {
                "name": name,
                "values": {
                    key: {"uniform": list(value)} if isinstance(value, tuple) else value
                    for key, value in (values or {}).items()
                },
                "types": [
                    {
                        "name": kind,
                        "weight": (weights or {}).get(kind, 1),
                        "values": dict(kind_values),
                    }
                    for kind, kind_values in (types or {}).items()
                ],
                "order": order,
            }
        )

    def set_rate_rule(self, *, min_trials: int, up: float, down: float) -> None:
        """Move a level up or down by the correct rate of the trials at the level."""
        self._progression = {
            "rule": "rate",
            "minTrials": min_trials,
            "up": up,
            "down": down,
        }

    def set_count_rule(self, correct: int) -> None:
        """Move a level up after this many correct trials at the level."""
        self._progression = {"rule": "count", "correct": correct}

    # ---- Python hooks --------------------------------------------------------

    def on_trial(self, hook: Hook) -> Hook:
        """Call ``hook(scene)`` before each trial; it may change ``scene.values``."""
        self._hooks.on_trial.append(hook)
        return hook

    def on_enter(self, state: str, hook: Hook) -> Hook:
        """Call ``hook(scene)`` each time ``state`` is entered.

        The hook has the framework at hand (``scene.mxbiflow``), can send the machine
        an event (``scene.fire("fast")`` is ``host.fast``) and can keep values in the
        trial's record (``scene.note``).
        """
        self._hooks.on_enter.setdefault(state, []).append(hook)
        return hook

    # ---- the result ----------------------------------------------------------

    def build(self) -> tuple[Stage, Hooks]:
        """The stage as data, and its hooks; raises ``ValueError`` for a wrong name."""
        self._check()
        stage = Stage.model_validate(
            {
                "name": self.name,
                "machine": {
                    "channels": {"inputs": self._inputs, "outputs": self._outputs},
                    "parameters": self._parameters,
                    "timers": self._timers,
                    "generators": self._generators,
                    "counters": self._counters,
                    "start": self._start,
                    "groups": list(self._groups.values()),
                    "states": list(self._states.values()),
                    "layout": {},
                    "screen": {"width": self._screen[0], "height": self._screen[1]},
                    "stimuli": list(self._stimuli.values()),
                },
                "outcomes": self._outcomes,
                "levels": self._levels
                or [{"name": "1", "values": {}, "types": [], "order": "random"}],
                "progression": self._progression,
            }
        )
        return stage, self._hooks

    def _check(self) -> None:
        """Names that lead nowhere would fail silently in a trial: refuse them here."""
        problems: list[str] = []
        if self._start not in self._states:
            problems.append(f'the start state "{self._start}" does not exist')
        targets = {p["name"] for p in self._parameters if p["type"] == "state"}
        startable = {t["name"] for t in self._timers + self._generators}
        counters = {c["name"] for c in self._counters}
        sounds = {n for n, s in self._stimuli.items() if s["kind"] in ("wav", "tones")}
        visuals = set(self._stimuli) - sounds
        for holder in (*self._states.values(), *self._groups.values()):
            where = holder["name"]
            if holder["group"] is not None and holder["group"] not in self._groups:
                problems.append(f'{where}: no group "{holder["group"]}"')
            for output in holder["hold"]:
                if output not in self._outputs:
                    problems.append(f'{where}: no output "{output}"')
            for transition in holder["transitions"]:
                target = transition["target"]
                if isinstance(target, dict):
                    if target["param"] not in targets:
                        problems.append(
                            f'{where}: no state parameter "{target["param"]}"'
                        )
                elif target != EXIT and target not in self._states:
                    problems.append(f'{where}: no state "{target}"')
            for action in holder.get("onEntry", []):
                (kind, name), *_ = action.items()
                known = {
                    "show": visuals,
                    "hide": visuals,
                    "play": sounds,
                    "start": startable,
                    "stop": startable | sounds,
                    "reset": counters,
                }.get(kind)
                if known is not None and name not in known:
                    problems.append(f'{where}: {kind} "{name}" does not exist')
        for state in (*self._outcomes, *self._hooks.on_enter):
            if state not in self._states:
                problems.append(f'no state "{state}" for an outcome or a hook')
        if problems:
            raise ValueError(f'stage "{self.name}": ' + "; ".join(problems))


def stage_scenes(
    *stages: StageBuilder,
    animal_values: Mapping[str, Mapping[str, Fixed]] | None = None,
) -> dict[str, type[Scene]]:
    """The scenes of stages written in Python, to register with the scene manager.

    Past a stage's last level an animal moves to the next stage given, and below its
    first to the previous one. ``animal_values`` are parameter values of single
    animals, by animal name; they replace a level's and a trial type's.
    """
    built = [stage.build() for stage in stages]
    first = built[0][0]
    experiment = Experiment.model_validate(
        {
            "stages": [stage for stage, _ in built],
            # Stage and level come from the session; the format wants them filled.
            "animals": [
                {
                    "name": animal,
                    "stage": first.name,
                    "level": first.levels[0].name,
                    "values": dict(values),
                }
                for animal, values in (animal_values or {}).items()
            ],
        }
    )
    return machine_scenes(experiment, {stage.name: hooks for stage, hooks in built})
