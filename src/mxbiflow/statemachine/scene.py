"""Runs a cogforge experiment's stages in the game loop, one scene per trial.

Without cagelab-2 the machine is evaluated once per frame: timeouts, timers, sounds and
outputs have one-frame resolution. An input change carries the time its channel gives
it, which for a GPIO pin is when the edge happened. Register the scenes of
:func:`machine_scenes` with the scene manager; the scheduler then starts the scene of
the animal's stage for each trial.

The experiment only names its channels; the rig wires each name to a device or a GPIO
pin (``channels`` in the hardware configuration, :mod:`mxbiflow.driver.channels`). The
touchscreen needs no wiring. The trial's life cycle is :class:`~mxbiflow.scene.TrialScene`'s: a
stopped trial (the animal left, the run ended) is recorded but does not count towards
the level rules.
"""

import io
from collections.abc import Callable, Collection, Hashable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from time import monotonic
from typing import ClassVar
from urllib.request import urlopen

import pygame
import soundfile
from pydantic import BaseModel, JsonValue
from pygame import Surface
from pygame.event import Event

from ..context import get_mxbiflow
from ..driver.audioplayer.audioplayer import AudioPlayer, LoadedWav, PlayTask
from ..driver.audioplayer.puretone_generator import PureToneGenerator, PureToneUnit
from ..driver.channels import InputChannel, OutputChannel
from ..scene.scene import Scene
from ..scene.settlement import SettlementAction
from ..scene.trial_scene import TrialScene
from .host import (
    ACTIONS,
    Outcome,
    Progress,
    draw_trial,
    outcome_of,
    record_of,
    settle,
)
from .models import (
    BackgroundStimulus,
    CircleStimulus,
    CrossStimulus,
    Experiment,
    ImageStimulus,
    Machine,
    RectStimulus,
    Stage,
    TonesStimulus,
    WavStimulus,
)
from .runner import (
    Trial,
    Values,
    VisualStimulus,
    amount_in,
    duration_of,
    place_of,
)
from .validate import check_experiment

_CONTEXT = "machine"

type Sound = WavStimulus | TonesStimulus


class Cursor(BaseModel):
    """The next row of each factor that ``level`` of a stage takes in turn.

    Kept in the stage's context; the level's counts are the session's.
    """

    level: int
    cursors: dict[str, int] = {}


type Hook = Callable[["MachineScene"], None]


def check_channels(
    stage: Stage, inputs: Collection[str], outputs: Collection[str]
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
class Hooks:
    """A stage's own Python code, run by the host around the machine.

    The machine stays data: what it does is in its states and transitions. A hook is
    for what the data cannot say, such as picking this trial's values from a sequence
    or grading a reward. It gets the trial's :class:`MachineScene`.
    """

    #: Called before the trial starts; may change ``scene.values``.
    on_trial: list[Hook] = field(default_factory=list["Hook"])
    #: By state name: called once each time the state is entered.
    on_enter: dict[str, list[Hook]] = field(default_factory=dict[str, list["Hook"]])


def machine_scenes(
    experiment: Experiment, hooks: Mapping[str, Hooks] | None = None
) -> dict[str, type[Scene]]:
    """One scene class per stage of ``experiment``, by stage name.

    ``hooks`` gives stages their Python code, by stage name. A stage that uses a
    channel the rig does not wire raises ``ValueError`` when its first trial is made,
    before the trial starts. An experiment whose levels cannot be drawn (a parameter
    set twice, a factor without rows, a stimulus of the wrong kind) raises here.
    """
    check_experiment(experiment)
    return {
        stage.name: type(
            f"MachineScene[{stage.name}]",
            (MachineScene,),
            {
                "experiment": experiment,
                "stage_index": index,
                "hooks": (hooks or {}).get(stage.name, Hooks()),
                "level_table": {"default": list(range(1, len(stage.levels) + 1))},
                "_surfaces": {},
                "_sounds": {},
            },
        )
        for index, stage in enumerate(experiment.stages)
    }


class MachineScene(TrialScene):
    """One trial of one stage; :func:`machine_scenes` makes the class of each stage.

    The session's level ``n`` is the stage's ``n``-th level, counted from 1.
    """

    experiment: ClassVar[Experiment]
    stage_index: ClassVar[int]
    hooks: ClassVar[Hooks]
    # Decoded pictures and sounds of the stage, kept across its trials.
    _surfaces: ClassVar[dict[str, Surface | None]]
    _sounds: ClassVar[dict[Hashable, LoadedWav | list[PureToneUnit] | None]]

    @classmethod
    def name(cls) -> str:
        return cls.experiment.stages[cls.stage_index].name

    def __init__(self) -> None:
        # What cannot run fails here, before the trial is counted.
        context = get_mxbiflow()
        mxbi = context.mxbi
        self._stage = self.experiment.stages[self.stage_index]
        self._machine: Machine = self._stage.machine
        check_channels(self._stage, mxbi.inputs, mxbi.outputs)
        self._inputs: dict[str, InputChannel] = {
            name: mxbi.inputs[name] for name in self._machine.channels.inputs
        }
        self._outputs: dict[str, OutputChannel] = {
            name: mxbi.outputs[name] for name in self._machine.channels.outputs
        }
        # The animal's screen: the rig's, turned a quarter when the experiment is laid
        # out upright and the rig's framebuffer lies on its side (or the reverse).
        rig = (mxbi.screen_size.width, mxbi.screen_size.height)
        reference = self._machine.screen
        self._rotated = (reference.width > reference.height) != (rig[0] > rig[1])
        self._screen: tuple[int, int] = (rig[1], rig[0]) if self._rotated else rig
        # A level outside the stage's (a new animal's 0, one set by hand) is brought in.
        state = context.session.require_current_animal().current_stage
        level = min(max(state.level, 1), len(self._stage.levels))
        if level != state.level:
            state.reset_level(level)
        super().__init__()
        self._aplayer: AudioPlayer = mxbi.aplayer

        progress = self._load_progress()
        own = next(
            (a.values for a in self.experiment.animals if a.name == self.animal.name),
            {},
        )
        self._draw = draw_trial(self.experiment, own, progress)
        self._progress = replace(progress, cursors=self._draw.cursors)
        self._settled: Progress = self._progress
        self._outcome: Outcome = "none"
        self._values: Values = self._draw.values
        self._extra: dict[str, JsonValue] = {}
        self._entered = 0

        self._trial: Trial | None = None
        self._started = 0.0
        # Touches since the last frame: when, and where on the machine's screen.
        self._touches: list[tuple[float, float, float]] = []
        self._high: set[str] = set()
        self._playing: dict[str, tuple[float, PlayTask | None]] = {}
        self._frame: tuple[list[str], Surface] | None = None

    # ---- TrialScene ----------------------------------------------------------

    def begin(self) -> None:
        for hook in self.hooks.on_trial:
            hook(self)
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
        self._run_hooks()
        self._apply(0)

    def end(self) -> None:
        if self._trial is None:
            return
        now = self._now()
        self._trial.stop(now)
        self._apply(now)
        self._outcome = outcome_of(self._stage, self._trial)

    def decide(self) -> SettlementAction:
        self._settled, action = settle(self.experiment, self._progress, self._outcome)
        self.session.count_trial(self._outcome == "correct")
        return next(a for a, name in ACTIONS.items() if name == action)

    def record(self) -> BaseModel:
        assert self._trial is not None
        return record_of(
            self.experiment,
            self.animal.name,
            self.info.trial_id,
            self._progress,
            self._draw,
            self._trial,
            self._outcome,
            ACTIONS[self.action],
            self._extra,
        )

    def move(self, action: SettlementAction) -> None:
        settled = self._settled
        if action in (SettlementAction.NEXT_STAGE, SettlementAction.PREV_STAGE):
            self.session.enter_stage(
                self.experiment.stages[settled.stage].name, settled.level + 1
            )
        else:
            super().move(action)
        self.session.set_stage_context(
            _CONTEXT, Cursor(level=settled.level + 1, cursors=dict(settled.cursors))
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
        self._run_hooks()
        self._apply(now)
        if trial.state is None:
            outcome = outcome_of(self._stage, trial)
            self.resolve(None if outcome == "none" else outcome == "correct")
            self.finish()

    def draw(self, screen: Surface) -> None:
        shown = self._trial.shown if self._trial is not None else []
        if self._frame is None or self._frame[0] != shown:
            frame = self._render(shown)
            if self._rotated:
                frame = pygame.transform.rotate(frame, -90)
            self._frame = (list(shown), frame)
        screen.blit(self._frame[1], (0, 0))

    # ---- for the stage's hooks -----------------------------------------------

    @property
    def values(self) -> Values:
        """This trial's parameter values; an ``on_trial`` hook may change them."""
        return self._values

    @property
    def trial(self) -> Trial:
        """The running trial: its state, the states visited, its log."""
        if self._trial is None:
            raise RuntimeError("the trial has not started")
        return self._trial

    @property
    def now(self) -> float:
        """Milliseconds from the start of the trial."""
        return self._now()

    def fire(self, name: str) -> None:
        """Send the machine the event ``host.<name>``."""
        self.trial.host(name, max(self._now(), self.trial.now))

    def note(self, key: str, value: JsonValue) -> None:
        """Keep a value in the trial's record, under ``extra``."""
        self._extra[key] = value

    def _run_hooks(self) -> None:
        """Call the hooks of the states entered since the last call, in order."""
        trial = self.trial
        while self._entered < len(trial.visited):
            visit = trial.visited[self._entered]
            self._entered += 1
            for hook in self.hooks.on_enter.get(visit.state, []):
                hook(self)

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
        high = self._trial.outputs(now)
        for name in high - self._high:
            self._outputs[name].set(True)
        for name in self._high - high:
            self._outputs[name].set(False)
        self._high = high

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

    def _play(self, name: str) -> PlayTask | None:
        sound = self._sound(name)
        if sound is None:
            return None
        if isinstance(sound, LoadedWav):
            return self._aplayer.play_loaded_wav(sound)
        return self._aplayer.play_puretone_sequence(sound)

    def _sound(self, name: str) -> LoadedWav | list[PureToneUnit] | None:
        stimulus = next(s for s in self._machine.stimuli if s.name == name)
        assert isinstance(stimulus, (WavStimulus, TonesStimulus))
        if isinstance(stimulus, WavStimulus):
            if name not in self._sounds:
                type(self)._sounds[name] = _load_wav(stimulus)
            return self._sounds[name]
        # Tones may be this trial's: frequencies and lengths can be parameters.
        tones = tuple(
            (amount_in(self._values, t.frequency), amount_in(self._values, t.duration))
            for t in stimulus.tones
        )
        key = (name, tones, duration_of(stimulus, self._values))
        if key not in self._sounds:
            type(self)._sounds[key] = _tone_train(tones, key[2], self._aplayer)
        return self._sounds[key]

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
        if stimulus.name not in self._surfaces:
            surface = None
            if stimulus.image is not None:
                kind, data = _data(stimulus.image)
                if kind == "image/svg+xml":
                    surface = pygame.image.load_sized_svg(io.BytesIO(data), size)
                else:
                    loaded = pygame.image.load(io.BytesIO(data))
                    surface = pygame.transform.smoothscale(loaded.convert_alpha(), size)
            type(self)._surfaces[stimulus.name] = surface
        return self._surfaces[stimulus.name]

    # ---- the host's side -----------------------------------------------------

    def _load_progress(self) -> Progress:
        """Where the animal is: the session's stage, level and counts at the level."""
        state = self.animal.current_stage
        cursor = state.get_context(_CONTEXT, Cursor)
        return Progress(
            self.stage_index,
            state.level - 1,
            state.level_counted,
            state.level_correct,
            # A new level, or one set by hand, takes its rows from the first again.
            cursor.cursors
            if cursor is not None and cursor.level == state.level
            else {},
        )


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


def _load_wav(stimulus: WavStimulus) -> LoadedWav | None:
    if stimulus.sound is None:
        return None
    samples, sample_rate = soundfile.read(
        io.BytesIO(_data(stimulus.sound)[1]), dtype="int16", always_2d=True
    )
    return LoadedWav(
        pcm_bytes=samples.tobytes(),
        sample_rate=sample_rate,
        channels=samples.shape[1],
        sample_dtype="int16",
    )


def _tone_train(
    tones: Sequence[tuple[float, float]], duration: float, aplayer: AudioPlayer
) -> list[PureToneUnit]:
    """Tones of ``(Hz, ms)`` repeated until ``duration`` has passed; the last is cut."""
    generator = PureToneGenerator()
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
