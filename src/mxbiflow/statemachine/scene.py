"""Runs a cogforge experiment's stages in the game loop, one scene per trial.

Without cagelab-2 the machine is evaluated once per frame, so every time has one-frame
resolution. Register the scenes of :func:`machine_scenes` with the scene manager; the
scheduler then starts the scene of the animal's stage for each trial.

The experiment only names its channels; the rig's wiring says which device each one is
(``channels`` in the hardware configuration, ``mxbi.json``): an input is high while its
detector sees an animal, an output runs its rewarder while it is high. The touchscreen
needs no mapping. The trial's life cycle is :class:`~mxbiflow.scene.TrialScene`'s: a
stopped trial (the animal left, the run ended) is recorded but does not count towards
the level rules.
"""

import io
from dataclasses import dataclass, field, replace
from typing import ClassVar
from urllib.request import urlopen

import pygame
import soundfile
from pydantic import BaseModel
from pygame import Surface
from pygame.event import Event

from ..core.context import get_mxbiflow
from ..driver.audioplayer.audioplayer import AudioPlayer, LoadedWav, PlayTask
from ..driver.audioplayer.puretone_generator import PureToneGenerator, PureToneUnit
from ..driver.detector.detector import Detector
from ..driver.rewarder.rewarder import Rewarder
from ..gameloop.settlement import SettlementAction
from ..scene.scene import Scene
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
    TextStimulus,
    TonesStimulus,
    WavStimulus,
)
from .runner import Trial, Values, amount_in

_CONTEXT = "machine"
# The rewarder runs for a given time; a held output asks for this long and stops it.
_HOLD_MS = 600_000

type VisualStimulus = (
    ImageStimulus | CircleStimulus | RectStimulus | CrossStimulus | TextStimulus
)
type Sound = WavStimulus | TonesStimulus


class Cursor(BaseModel):
    """The next trial type at ``level`` of a stage that takes them in turn.

    Kept in the stage's context; the level's counts are the session's.
    """

    level: int
    cursor: int = 0


@dataclass(frozen=True)
class Wiring:
    """A rig's channels by name: which of its devices each one is.

    The rig configuration's ``channels``; given to :func:`machine_scenes` instead, it
    replaces them (tests, a rig without the configuration).
    """

    #: Input name to detector id.
    inputs: dict[str, int] = field(default_factory=dict)
    #: Output name to rewarder id.
    outputs: dict[str, int] = field(default_factory=dict)


def check_channels(stage: Stage, channels: Wiring) -> None:
    """Raise ``ValueError`` when the stage uses a channel the rig does not wire."""
    missing = [
        f'{kind} "{name}"'
        for kind, names, mapped in (
            ("input", stage.machine.channels.inputs, channels.inputs),
            ("output", stage.machine.channels.outputs, channels.outputs),
        )
        for name in names
        if name not in mapped
    ]
    if missing:
        raise ValueError(
            f'stage "{stage.name}" uses {", ".join(missing)}, which this rig does not '
            "wire: add them under channels in the hardware configuration (mxbi.json)"
        )


def machine_scenes(
    experiment: Experiment, wiring: Wiring | None = None
) -> dict[str, type[Scene]]:
    """One scene class per stage of ``experiment``, by stage name.

    The channels are wired by the rig configuration, or by ``wiring`` when given. A
    stage that uses a channel without a wire raises ``ValueError``: here for a given
    ``wiring``, else when its first trial is made, before the trial starts.
    """
    if wiring is not None:
        for stage in experiment.stages:
            check_channels(stage, wiring)
    return {
        stage.name: type(
            f"MachineScene[{stage.name}]",
            (MachineScene,),
            {
                "experiment": experiment,
                "wiring": wiring,
                "stage_index": index,
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
    wiring: ClassVar[Wiring | None]
    stage_index: ClassVar[int]
    # Decoded pictures and sounds of the stage, kept across its trials.
    _surfaces: ClassVar[dict[str, Surface | None]]
    _sounds: ClassVar[dict[str, LoadedWav | list[PureToneUnit] | None]]

    @classmethod
    def name(cls) -> str:
        return cls.experiment.stages[cls.stage_index].name

    def __init__(self) -> None:
        # What cannot run fails here, before the trial is counted.
        context = get_mxbiflow()
        mxbi = context.mxbi
        self._stage = self.experiment.stages[self.stage_index]
        self._machine: Machine = self._stage.machine
        channels = self.wiring
        if channels is None:
            rig = context.session.mxbi_config.channels
            channels = Wiring(inputs=rig.inputs, outputs=rig.outputs)
            check_channels(self._stage, channels)
        self._inputs: dict[str, Detector] = {
            name: mxbi.get_detector(channels.inputs[name])
            for name in self._machine.channels.inputs
        }
        self._outputs: dict[str, Rewarder] = {
            name: mxbi.get_rewarder(channels.outputs[name])
            for name in self._machine.channels.outputs
        }
        self._rotated = self._screen_rotated(
            (mxbi.screen_size.width, mxbi.screen_size.height)
        )
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
        self._progress = replace(progress, cursor=self._draw.cursor)
        self._settled: Progress = self._progress
        self._outcome: Outcome = "none"
        self._values: Values = self._draw.values

        self._trial: Trial | None = None
        self._started_ms = 0
        self._high: set[str] = set()
        self._playing: dict[str, tuple[float, PlayTask | None]] = {}
        self._frame: tuple[list[str], Surface] | None = None

    # ---- TrialScene ----------------------------------------------------------

    def begin(self) -> None:
        self._started_ms = pygame.time.get_ticks()
        # The rig reports its own inputs, a photodiode among them: none is simulated.
        self._trial = Trial(
            self._machine, self._read_inputs(), 0, self._values, photodiode=False
        )
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
            _CONTEXT, Cursor(level=settled.level + 1, cursor=settled.cursor)
        )

    def handle_event(self, event: Event) -> None:
        if not self._running or self._trial is None:
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            x, y = event.pos
            if self._rotated:
                x, y = y, self._machine.screen.height - x
            self._trial.touch(x, y, self._now())

    def update(self, dt_s: float) -> None:
        if not self._running or self._trial is None:
            return
        now = self._now()
        for name, high in self._read_inputs().items():
            self._trial.set_input(name, high, now)
        self._trial.advance(now)
        self._apply(now)
        if self._trial.state is None:
            outcome = outcome_of(self._stage, self._trial)
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

    # ---- the rig -------------------------------------------------------------

    def _now(self) -> int:
        return pygame.time.get_ticks() - self._started_ms

    def _read_inputs(self) -> dict[str, bool]:
        return {
            name: detector.current_animal is not None
            for name, detector in self._inputs.items()
        }

    def _screen_rotated(self, rig: tuple[int, int]) -> bool:
        """Whether the animal's upright screen is the rig's screen turned a quarter."""
        size = (self._machine.screen.width, self._machine.screen.height)
        if size == rig:
            return False
        if size[::-1] == rig:
            return True
        raise ValueError(
            f'stage "{self._stage.name}" is laid out for a {size[0]}×{size[1]} '
            f"screen; this rig's is {rig[0]}×{rig[1]}"
        )

    def _apply(self, now: float) -> None:
        """Drive the outputs and sounds to what the trial says they are at ``now``."""
        if self._trial is None:
            return
        high = self._trial.outputs(now)
        for name in high - self._high:
            self._outputs[name].give_reward(_HOLD_MS)
        for name in self._high - high:
            self._outputs[name].stop_reward()
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
        if name not in self._sounds:
            stimulus = next(s for s in self._machine.stimuli if s.name == name)
            assert isinstance(stimulus, (WavStimulus, TonesStimulus))
            type(self)._sounds[name] = (
                _load_wav(stimulus)
                if isinstance(stimulus, WavStimulus)
                else _tone_train(stimulus, self._aplayer)
            )
        return self._sounds[name]

    # ---- the screen ----------------------------------------------------------

    def _render(self, shown: list[str]) -> Surface:
        screen = self._machine.screen
        frame = Surface((screen.width, screen.height))
        stimuli = {stimulus.name: stimulus for stimulus in self._machine.stimuli}
        for name in shown:
            stimulus = stimuli[name]
            if isinstance(stimulus, BackgroundStimulus):
                frame.fill(stimulus.color)
            elif not isinstance(stimulus, (WavStimulus, TonesStimulus)):
                self._render_visual(frame, stimulus)
        return frame

    def _render_visual(self, frame: Surface, stimulus: VisualStimulus) -> None:
        x = amount_in(self._values, stimulus.x)
        y = amount_in(self._values, stimulus.y)
        w, h = stimulus.width, stimulus.height
        box = pygame.Rect(0, 0, round(w), round(h))
        box.center = (round(x), round(y))
        if isinstance(stimulus, ImageStimulus):
            image = self._image(stimulus)
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

    def _image(self, stimulus: ImageStimulus) -> Surface | None:
        if stimulus.name not in self._surfaces:
            surface = None
            if stimulus.image is not None:
                size = (round(stimulus.width), round(stimulus.height))
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
            # A new level, or one set by hand, takes its types from the first again.
            cursor.cursor if cursor is not None and cursor.level == state.level else 0,
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


def _tone_train(stimulus: TonesStimulus, aplayer: AudioPlayer) -> list[PureToneUnit]:
    """The tones repeated until the stimulus's duration has passed; the last is cut."""
    generator = PureToneGenerator()
    table = aplayer.frequency_response_table
    units: list[PureToneUnit] = []
    left = stimulus.duration
    while left > 0 and stimulus.tones:
        for tone in stimulus.tones:
            if left <= 0:
                break
            length = min(tone.duration, left)
            frequency = round(tone.frequency)
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
