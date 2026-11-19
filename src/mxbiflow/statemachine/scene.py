"""Runs a stage's trial state machine in the game loop, one scene per trial.

The scheduler makes a scene for each trial of the animal's stage. What the trial does
is its machine, which is data. Which values the trial gets, and what its record does to
the animal's level, is the stage's Python (:class:`~.stage.Stage`), whose trial is a
:class:`MachineTrial`. The stages of a cogforge file (:func:`machine_scenes`) run with
their parameters' defaults.

Without cagelab-2 the machine is evaluated once per frame: timeouts, timers, sounds and
outputs have one-frame resolution. An input change carries the time its channel gives
it, which for a GPIO pin is when the edge happened.

The machine only names its channels; the rig wires each name to a device or a GPIO pin
(``channels`` in the hardware configuration, :mod:`mxbiflow.driver.channels`). The
touchscreen needs no wiring. The trial's life cycle is
:class:`~mxbiflow.scene.TrialScene`'s.
"""

import io
import logging
from abc import abstractmethod
from collections.abc import Callable, Collection, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, ClassVar
from urllib.request import urlopen

import pygame
from pydantic import BaseModel, JsonValue
from pygame import Surface
from pygame.event import Event

from ..driver.audioplayer import (
    AudioPlayer,
    PureToneGenerator,
    PureToneUnit,
    Sound,
    read_sound,
    tone_train,
)
from ..driver.channels import InputChannel, OutputChannel
from ..scene.scene import Scene
from ..scene.settlement import SettlementAction
from ..scene.trial_scene import TrialScene
from ..task import Task
from .host import ACTIONS, Entered, Logged, Outcome, TrialRecord, outcome_of
from .machine import Machine, TrialParams
from .models import (
    BackgroundStimulus,
    CircleStimulus,
    CrossStimulus,
    Experiment,
    ImageStimulus,
    Outcomes,
    RectStimulus,
    TonesStimulus,
    WavStimulus,
)
from .models import Stage as StageData
from .runner import (
    Trial,
    Values,
    VisualStimulus,
    amount_in,
    default_values,
    duration_of,
    place_of,
)
from .stage import Stage, stage_of
from .validate import machine_problems, value_problems

logger = logging.getLogger(__name__)


def check_channels(
    stage: StageData, inputs: Collection[str], outputs: Collection[str]
) -> None:
    """Raise ``ValueError`` when the stage uses a channel the rig does not wire."""
    missing = [
        f'{kind} "{name}"'
        for kind, names, wired in (
            ("input", stage.machine.channels.inputs, inputs),
            ("output", stage.machine.channels.outputs, outputs),
        )
        for name in names
        if name not in wired
    ]
    if missing:
        raise ValueError(
            f'stage "{stage.name}" uses {", ".join(missing)}, which this rig does not '
            "wire: add them under channels in the hardware configuration (mxbi.json)"
        )


@dataclass
class Loaded:
    """A stage's machine as the format's data, with what was decoded for it."""

    stage: StageData
    # Decoded pictures and sounds, kept across the stage's trials.
    surfaces: dict[str, Surface | None] = field(
        default_factory=dict[str, Surface | None]
    )
    sounds: dict[Hashable, Sound | None] = field(
        default_factory=dict[Hashable, Sound | None]
    )


def on_enter[F: Callable[..., None]](*states: str) -> Callable[[F], F]:
    """Mark a stage's method to be called each time one of ``states`` is entered.

    It runs in the frame after the state was entered, so what it decides has one-frame
    resolution; what must be exact belongs in the machine.
    """

    def mark(method: F) -> F:
        method.__dict__["on_enter_states"] = tuple(str(state) for state in states)
        return method

    return mark


def machine_scenes(experiment: Experiment) -> dict[str, type[Scene]]:
    """One scene class per stage of a cogforge file, by stage name.

    Each trial runs with the parameters' defaults: a file has the trial's machine, not
    which values a trial gets. A machine that cannot run as written raises here.
    """
    scenes: dict[str, type[Scene]] = {}
    for stage in experiment.stages:
        problems = machine_problems(stage.machine)
        if problems:
            raise ValueError(f'stage "{stage.name}": ' + "; ".join(problems))
        scenes[stage.name] = type(
            f"MachineScene[{stage.name}]",
            (_FileScene,),
            {"loaded": Loaded(stage=stage)},
        )
    return scenes


class MachineScene(TrialScene):
    """One trial of a stage whose trial is a state machine.

    A subclass says which machine (``load``) and which values this trial gets
    (``values``). The rest is :class:`~mxbiflow.scene.TrialScene`: ``settlement`` or
    ``decide`` move the animal between levels, as in any stage; ``outcome`` and
    ``trial`` say how the trial went.
    """

    # By state: the names of the methods marked with ``on_enter``.
    _entry_methods: ClassVar[dict[str, list[str]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        methods: dict[str, list[str]] = {}
        for name in dir(cls):
            states = getattr(getattr(cls, name, None), "on_enter_states", ())
            for state in states:
                methods.setdefault(state, []).append(name)
        cls._entry_methods = methods

    # ---- the stage -----------------------------------------------------------

    @abstractmethod
    def load(self) -> Loaded:
        """The stage's machine; the same object for trials of the same machine."""

    def values(self) -> Mapping[str, float | str]:
        """This trial's parameter values; one left out takes its default."""
        return {}

    # ---- the trial -----------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        mxbi = self.mxbiflow.mxbi
        self._loaded = self.load()
        self._stage = self._loaded.stage
        self._machine = self._stage.machine
        unknown = set(self._entry_methods) - {s.name for s in self._machine.states}
        if unknown:
            raise ValueError(
                f'stage "{self._stage.name}": on_enter of no state: {sorted(unknown)}'
            )
        check_channels(self._stage, mxbi.inputs, mxbi.outputs)
        self._inputs: dict[str, InputChannel] = {
            name: mxbi.inputs[name] for name in self._machine.channels.inputs
        }
        self._outputs: dict[str, OutputChannel] = {
            name: mxbi.outputs[name] for name in self._machine.channels.outputs
        }
        # The animal's screen: the rig's, turned a quarter when the machine is laid
        # out upright and the rig's framebuffer lies on its side (or the reverse).
        rig = (mxbi.screen_size.width, mxbi.screen_size.height)
        reference = self._machine.screen
        self._rotated = (reference.width > reference.height) != (rig[0] > rig[1])
        self._screen: tuple[int, int] = (rig[1], rig[0]) if self._rotated else rig
        self._aplayer: AudioPlayer = mxbi.aplayer

        given = dict(self.values())
        problems = value_problems(self._machine, given)
        if problems:
            raise ValueError(
                f'stage "{self._stage.name}": the values of the trial: '
                + "; ".join(problems)
            )
        self._values: Values = {**default_values(self._machine), **given}
        self._outcome: Outcome = "none"
        self._extra: dict[str, JsonValue] = {}
        self._entered = 0

        self._trial: Trial | None = None
        self._started = 0.0
        # Touches since the last frame: when, and where on the machine's screen.
        self._touches: list[tuple[float, float, float]] = []
        # How many of the trial's output changes have been given to the rig.
        self._applied = 0
        self._failed = False
        self._playing: dict[str, tuple[float, Task | None]] = {}
        self._frame: tuple[list[str], Surface] | None = None

    # ---- TrialScene ----------------------------------------------------------

    def begin(self) -> None:
        self._check_places()
        self._started = monotonic()
        levels: dict[str, bool] = {}
        for name, channel in self._inputs.items():
            channel.changes()  # what happened before the trial is not its events
            levels[name] = channel.level()
        # The rig reports its own inputs, a photodiode among them: none is simulated.
        self._trial = Trial(
            self._machine,
            levels,
            0,
            self._values,
            photodiode=False,
            screen=self._screen,
        )
        self._run_entries()
        self._apply(0)
        self._resolve_known()

    def end(self) -> None:
        if self._trial is None:
            return
        now = self._now()
        self._trial.stop(now)
        self._apply(now)
        self._outcome = outcome_of(self._stage, self._trial)

    def record(self) -> TrialRecord:
        trial = self.trial
        return TrialRecord(
            animal=self.animal.name,
            trial=self.info.trial_id,
            stage=self._stage.name,
            level=self.info.level,
            values=self._values,
            outcome=self._outcome,
            error=trial.error,
            action=ACTIONS[self.action],
            states=[Entered(state=v.state, t=v.t) for v in trial.visited],
            events=[Logged(t=entry.t, text=entry.text) for entry in trial.log],
            extra=self._extra,
        )

    def handle_event(self, event: Event) -> None:
        if not self._running or self._trial is None:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            if self._rotated:
                x, y = y, self._screen[1] - x
            self._touches.append((self._now(), x, y))

    def update(self, dt_s: float) -> None:
        trial = self._trial
        if not self._running or trial is None:
            return
        now = self._now()
        # Touches and input changes since the last frame, in the order they happened.
        events: list[tuple[float, Callable[[float], None]]] = [
            (at, lambda t, x=x, y=y, trial=trial: trial.touch(x, y, t))
            for at, x, y in self._touches
        ]
        self._touches = []
        for name, channel in self._inputs.items():
            for at, high in channel.changes():
                events.append(
                    (
                        self._ms(at),
                        lambda t, name=name, high=high, trial=trial: trial.set_input(
                            name, high, t
                        ),
                    )
                )
        for at, apply in sorted(events, key=lambda event: event[0]):
            apply(min(max(at, trial.now), now))
        trial.advance(now)
        self._run_entries()
        self._apply(now)
        self._resolve_known()
        if trial.state is None:
            self.finish()

    def draw(self, screen: Surface) -> None:
        shown = self._trial.shown if self._trial is not None else []
        if self._frame is None or self._frame[0] != shown:
            frame = self._render(shown)
            if self._rotated:
                frame = pygame.transform.rotate(frame, -90)
            self._frame = (list(shown), frame)
        screen.blit(self._frame[1], (0, 0))

    # ---- for the stage's own code -------------------------------------------

    @property
    def trial(self) -> Trial:
        """The running trial: its state, the states visited, its log."""
        if self._trial is None:
            raise RuntimeError("the trial has not started")
        return self._trial

    @property
    def outcome(self) -> Outcomes | None:
        """The trial's outcome so far: that of the last state entered that has one."""
        outcome = outcome_of(self._stage, self.trial)
        return None if outcome == "none" else Outcomes(outcome)

    @property
    def now_ms(self) -> float:
        """Milliseconds from the start of the trial."""
        return self._now()

    def fire(self, name: str) -> None:
        """Send the machine the event ``host.<name>``."""
        self.trial.host(name, max(self._now(), self.trial.now))

    def note(self, extra: BaseModel) -> None:
        """Keep a model's fields in the trial's record, under ``extra``."""
        self._extra.update(extra.model_dump(mode="json"))

    def _resolve_known(self) -> None:
        """Give the framework the outcome as soon as a state has decided one.

        The trial may go on (a reward, the time between trials); once its outcome is
        known it is settled even when the animal leaves before it ends.
        """
        outcome = self.outcome
        if outcome is not None:
            self.resolve(outcome is Outcomes.correct)

    def _run_entries(self) -> None:
        """Call the ``on_enter`` methods of the states entered since the last call."""
        trial = self.trial
        while self._entered < len(trial.visited):
            visit = trial.visited[self._entered]
            self._entered += 1
            for method in self._entry_methods.get(visit.state, []):
                getattr(self, method)()

    # ---- the rig -------------------------------------------------------------

    def _ms(self, at: float) -> float:
        """A ``monotonic()`` time as milliseconds from the start of the trial."""
        return round((at - self._started) * 1000, 3)

    def _now(self) -> float:
        return self._ms(monotonic())

    def _check_places(self) -> None:
        """Raise ``ValueError`` for a stimulus this trial cannot show on this screen."""
        width, height = self._screen
        for stimulus in self._machine.stimuli:
            if isinstance(stimulus, (BackgroundStimulus, WavStimulus, TonesStimulus)):
                continue
            place = place_of(stimulus, self._values, self._screen)
            if not (0 <= place.x <= width and 0 <= place.y <= height):
                raise ValueError(
                    f'stage "{self._stage.name}": the centre of "{stimulus.name}" is '
                    "outside the screen (positions are fractions from 0 to 1)"
                )
            if place.width > width or place.height > height:
                raise ValueError(
                    f'stage "{self._stage.name}": "{stimulus.name}" does not fit '
                    f"this rig's {width}×{height} screen"
                )

    def _apply(self, now: float) -> None:
        """Drive the outputs and sounds to what the trial says they are at ``now``."""
        if self._trial is None:
            return
        # Every change of an output since the last frame, in order: a pulse shorter
        # than a frame is still given.
        changes = self._trial.changes
        for edge in changes[self._applied :]:
            self._outputs[edge.output].set(edge.high)
        self._applied = len(changes)
        if self._trial.error is not None and not self._failed:
            self._failed = True
            logger.error(
                'stage "%s": the trial ended by an error of its machine: %s',
                self._stage.name,
                self._trial.error_detail,
            )

        sounds = self._trial.sounds
        for name, (end, task) in list(self._playing.items()):
            if sounds.get(name) == end:
                continue
            # A sound that played to its end stops by itself; any other is cut.
            if task is not None and now < end:
                task.cancel()
            del self._playing[name]
        for name, end in sounds.items():
            if name not in self._playing:
                self._playing[name] = (end, self._play(name))

    def _play(self, name: str) -> Task | None:
        sound = self._sound(name)
        return None if sound is None else self._aplayer.play(sound)

    def _sound(self, name: str) -> Sound | None:
        """The stimulus's sound in the output's format, made once and kept."""
        stimulus = next(s for s in self._machine.stimuli if s.name == name)
        assert isinstance(stimulus, (WavStimulus, TonesStimulus))
        aplayer = self._aplayer
        if isinstance(stimulus, WavStimulus):
            if name not in self._loaded.sounds:
                self._loaded.sounds[name] = (
                    None
                    if stimulus.sound is None
                    else aplayer.prepare(
                        read_sound(io.BytesIO(_data(stimulus.sound)[1]))
                    )
                )
            return self._loaded.sounds[name]
        # Tones may be this trial's: frequencies and lengths can be parameters.
        tones = tuple(
            (amount_in(self._values, t.frequency), amount_in(self._values, t.duration))
            for t in stimulus.tones
        )
        key = (name, tones, duration_of(stimulus, self._values))
        if key not in self._loaded.sounds:
            sample_rate_hz = aplayer.format.sample_rate_hz
            units = _tone_units(tones, key[2], aplayer, sample_rate_hz)
            self._loaded.sounds[key] = aplayer.prepare(
                tone_train(units, sample_rate_hz=sample_rate_hz)
            )
        return self._loaded.sounds[key]

    # ---- the screen ----------------------------------------------------------

    def _render(self, shown: list[str]) -> Surface:
        frame = Surface(self._screen)
        stimuli = {stimulus.name: stimulus for stimulus in self._machine.stimuli}
        for name in shown:
            stimulus = stimuli[name]
            if isinstance(stimulus, BackgroundStimulus):
                frame.fill(stimulus.color)
            elif not isinstance(stimulus, (WavStimulus, TonesStimulus)):
                self._render_visual(frame, stimulus)
        return frame

    def _render_visual(self, frame: Surface, stimulus: VisualStimulus) -> None:
        place = place_of(stimulus, self._values, self._screen)
        w, h = place.width, place.height
        box = pygame.Rect(0, 0, round(w), round(h))
        box.center = (round(place.x), round(place.y))
        if isinstance(stimulus, ImageStimulus):
            image = self._image(stimulus, box.size)
            if image is not None:
                frame.blit(image, box)
            else:
                # No picture yet: a frame with the stimulus's name.
                pygame.draw.rect(frame, "#9ca3af", box, max(1, round(max(w, h) / 60)))
                _draw_text(frame, stimulus.name, "#9ca3af", h / 3, box.center)
        elif isinstance(stimulus, CircleStimulus):
            pygame.draw.ellipse(frame, stimulus.color, box)
        elif isinstance(stimulus, RectStimulus):
            frame.fill(stimulus.color, box)
        elif isinstance(stimulus, CrossStimulus):
            thick = round(min(w, h) / 6)
            for size in ((box.width, thick), (thick, box.height)):
                bar = pygame.Rect((0, 0), size)
                bar.center = box.center
                frame.fill(stimulus.color, bar)
        else:
            _draw_text(frame, stimulus.text, stimulus.color, h, box.center)

    def _image(self, stimulus: ImageStimulus, size: tuple[int, int]) -> Surface | None:
        if stimulus.name not in self._loaded.surfaces:
            surface = None
            if stimulus.image is not None:
                kind, data = _data(stimulus.image)
                if kind == "image/svg+xml":
                    surface = pygame.image.load_sized_svg(io.BytesIO(data), size)
                else:
                    loaded = pygame.image.load(io.BytesIO(data))
                    surface = pygame.transform.smoothscale(loaded.convert_alpha(), size)
            self._loaded.surfaces[stimulus.name] = surface
        return self._loaded.surfaces[stimulus.name]


class _FileScene(MachineScene):
    """A stage of a cogforge file: its machine with the parameters' defaults."""

    loaded: ClassVar[Loaded]

    @classmethod
    def name(cls) -> str:
        return cls.loaded.stage.name

    def load(self) -> Loaded:
        return self.loaded


class MachineTrial[P: TrialParams](MachineScene):
    """The trial of a stage written in Python: one run of a :class:`~.machine.Machine`.

    The trial keeps nothing from one run to the next. It gives its machine
    (``machine``), is given its values by its stage (:class:`~.stage.Stage`; ``given``
    is that instance of the machine's parameters) and gives back its record, which its
    stage reads to decide whether the animal moves. Its own code notes what the record
    should carry::

        class TouchingTrial(MachineTrial[Params]):
            def machine(self) -> Machine:
                return MACHINE

            @on_enter(S.GIVE)
            def note_reward(self) -> None:
                self.note(Reward(length_ms=self.given.reward_ms))

    It is registered through its stage: ``Touching.scene()``.
    """

    #: The stage the trial belongs to; set by :meth:`~.stage.Stage.scene`.
    stage_type: ClassVar[type[Stage[Any]]]
    # The machines built so far, by stage, with the model each was built from: the
    # same model is built once, another (a changed configuration) again.
    _built: ClassVar[dict[str, tuple[Machine, Loaded]]] = {}

    @classmethod
    def bound_stage(cls) -> type[Stage[Any]]:
        """The stage the trial was registered through."""
        if not hasattr(cls, "stage_type"):
            raise TypeError(
                f"{cls.__name__} is a stage's trial: register its stage's scene()"
            )
        return cls.stage_type

    @classmethod
    def name(cls) -> str:
        return cls.bound_stage().name()

    @abstractmethod
    def machine(self) -> Machine:
        """The trial's machine; return the same object while it does not change."""

    @property
    def stage(self) -> Stage[P]:
        """The animal's stage object."""
        return stage_of(self.bound_stage(), run=self.mxbiflow, animal=self.animal)

    def load(self) -> Loaded:
        machine = self.machine()
        built = self._built.get(self.name())
        if built is None or built[0] is not machine:
            built = (machine, Loaded(stage=machine.build(self.name())))
            MachineTrial._built[self.name()] = built
        return built[1]

    def values(self) -> Mapping[str, float | str]:
        self.given: P = self.stage.next_trial()
        return self.given.model_dump(mode="json", by_alias=True)

    def decide(self) -> SettlementAction:
        return self.stage.decide(self.record())


def _data(url: str) -> tuple[str, bytes]:
    """The media type and bytes of a ``data:`` URL, base64 or percent-encoded."""
    # The format allows only data: URLs here.
    with urlopen(url) as response:
        return response.headers.get_content_type(), response.read()


def _draw_text(
    frame: Surface, text: str, color: str, height: float, center: tuple[int, int]
) -> None:
    if not pygame.font.get_init():
        pygame.font.init()
    rendered = pygame.font.Font(None, max(1, round(height))).render(text, True, color)
    frame.blit(rendered, rendered.get_rect(center=center))


def _tone_units(
    tones: Sequence[tuple[float, float]],
    duration: float,
    aplayer: AudioPlayer,
    sample_rate_hz: int,
) -> list[PureToneUnit]:
    """Tones of ``(Hz, ms)`` repeated until ``duration`` has passed; the last is cut."""
    generator = PureToneGenerator(sample_rate=sample_rate_hz)
    table = aplayer.frequency_response_table
    units: list[PureToneUnit] = []
    left = duration
    while left > 0 and tones:
        for hz, ms in tones:
            if left <= 0:
                break
            length = min(ms, left)
            frequency = round(hz)
            units.append(
                generator.gen_stimulus_unit(
                    PureToneUnit(
                        frequency_hz=frequency,
                        duration_ms=round(length),
                        master_volume=(
                            table.get_volume_by_freq(frequency)
                            if table is not None and frequency > 0
                            else None
                        ),
                    )
                )
            )
            left -= length
    return units
