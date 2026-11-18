"""Runs one trial of a machine, as cogforge's ``src/model/simulate.ts`` does.

A port with the same semantics, so both pass cogforge's conformance cases: events are
handled one at a time, a state's transitions are tried before its groups' from the
innermost outwards, and level events hold for inputs already at that level when a state
is entered. Times are milliseconds from the start of the trial. Nothing here touches
hardware: the caller reports inputs and touches, lets time run with :meth:`Trial.advance`,
and reads what to show, play and drive from the trial.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .models import (
    Amount1,
    BackgroundStimulus,
    ClearAction,
    HideAction,
    Machine,
    ParamRef,
    PlayAction,
    ResetAction,
    ShowAction,
    StopAction,
    TonesStimulus,
    Transition,
    WavStimulus,
)

EXIT = "exit"
# The input that follows the screen when the photodiode is simulated.
PHOTODIODE = "screen_on"
FRAME_MS = 17
_MAX_STEPS = 1000

type Values = dict[str, float | str]
type Amount = Amount1 | ParamRef


@dataclass(frozen=True)
class Visit:
    state: str
    t: float


@dataclass(frozen=True)
class LogEntry:
    t: float
    text: str


def default_values(machine: Machine) -> Values:
    return {parameter.name: parameter.default for parameter in machine.parameters}


def amount_in(values: Values, amount: Amount) -> float:
    if isinstance(amount, Amount1):
        return amount.root
    found = values.get(amount.param)
    return found if isinstance(found, (int, float)) else 0


def target_in(values: Values, target: ParamRef | str) -> str:
    if isinstance(target, str):
        return target
    found = values.get(target.param)
    return found if isinstance(found, str) else EXIT


class Trial:
    """One trial of ``machine`` with this trial's parameter ``values``.

    ``inputs`` are the input levels when the trial starts. With ``photodiode`` an input
    called ``screen_on`` is simulated: it flashes for one frame, one frame after every
    change of the screen. A rig with a real photodiode reports it as any other input.
    """

    def __init__(
        self,
        machine: Machine,
        inputs: Mapping[str, bool] | None = None,
        t: float = 0,
        values: Values | None = None,
        *,
        photodiode: bool = True,
    ) -> None:
        self._machine = machine
        self._states = {state.name: state for state in machine.states}
        self._groups = {group.name: group for group in machine.groups}
        self._stimuli = {stimulus.name: stimulus for stimulus in machine.stimuli}
        self._photodiode = photodiode and PHOTODIODE in machine.channels.inputs

        #: The current state; ``None`` once the trial has ended.
        self.state: str | None = None
        self.values: Values = default_values(machine) if values is None else values
        #: Every state entered, with its time.
        self.visited: list[Visit] = []
        self.entered_at = t
        self.now = t
        self.inputs: dict[str, bool] = {
            name: bool(inputs and inputs.get(name)) for name in machine.channels.inputs
        }
        #: Stimuli on the screen, in the order they were shown (the last on top).
        self.shown: list[str] = []
        #: Sounds playing: when they end.
        self.sounds: dict[str, float] = {}
        self.counters: dict[str, int] = {}
        self.log: list[LogEntry] = []

        self._timed_out = False
        # Running timers and generators: when they are done (None runs until stopped).
        self._timers: dict[str, float] = {}
        self._generators: dict[str, float | None] = {}
        self._generator_starts: dict[str, float] = {}
        # The photodiode's coming changes.
        self._flashes: list[tuple[float, bool]] = []

        self._say(t, "trial starts")
        self._enter(machine.start, t, 0)

    # ---- what the host reads -------------------------------------------------

    def held(self) -> set[str]:
        """Outputs held high by the state and its groups."""
        if self.state is None:
            return set()
        return {
            output
            for name in self._holders(self.state)
            for output in (self._states.get(name) or self._groups[name]).hold
        }

    def outputs(self, t: float) -> set[str]:
        """Outputs high at ``t``: those held, and the running generators' pulses."""
        high = self.held()
        for generator in self._machine.generators:
            start = self._generator_starts.get(generator.name)
            if start is None:
                continue
            since = t - start - amount_in(self.values, generator.delay)
            if since < 0:
                continue
            period = amount_in(self.values, generator.period)
            count = amount_in(self.values, generator.count)
            pulse = since // period if period > 0 else 0
            if (count == 0 or pulse < count) and since - pulse * period < amount_in(
                self.values, generator.width
            ):
                high.add(generator.output)
        return high

    def stimulus_at(self, x: float, y: float) -> str | None:
        """The visual stimulus on top at a point of the screen, or ``None``."""
        for name in reversed(self.shown):
            stimulus = self._stimuli.get(name)
            if stimulus is None or isinstance(
                stimulus, (BackgroundStimulus, WavStimulus, TonesStimulus)
            ):
                continue
            if (
                abs(x - amount_in(self.values, stimulus.x)) <= stimulus.width / 2
                and abs(y - amount_in(self.values, stimulus.y)) <= stimulus.height / 2
            ):
                return name
        return None

    # ---- what the host reports -----------------------------------------------

    def advance(self, t: float) -> None:
        """Let time run to ``t``, handling everything that falls due, in order."""
        for _ in range(_MAX_STEPS):
            due = self._due()
            if not due or due[0][0] > t:
                break
            self.now = due[0][0]
            due[0][1]()
        self.now = t

    def set_input(self, name: str, high: bool, t: float) -> None:
        """An input changes at ``t``."""
        self.advance(t)
        self._set_level(name, high, t)

    def touch(self, x: float, y: float, t: float) -> None:
        """The animal touches the screen at ``(x, y)`` pixels of the machine's screen."""
        self.advance(t)
        if self.state is None:
            return
        self._fire([f"{self.stimulus_at(x, y) or 'screen'}.touch"], t, 0)

    def stop(self, t: float) -> None:
        """The host ends the trial."""
        self.advance(t)
        if self.state is not None:
            self._say(t, "trial stopped")
            self._end(t)

    # ---- the machine ---------------------------------------------------------

    def _say(self, t: float, text: str) -> None:
        self.log.append(LogEntry(t, text))

    def _holders(self, state: str) -> list[str]:
        """The state and its groups from the innermost outwards."""
        chain = [state]
        found = self._states.get(state)
        group = found.group if found else None
        while group is not None and group in self._groups and group not in chain:
            chain.append(group)
            group = self._groups[group].group
        return chain

    def _set_screen(self, shown: list[str], t: float) -> None:
        changed = shown != self.shown
        self.shown = shown
        if changed and self._photodiode:
            self._flashes = [
                *(flash for flash in self._flashes if flash[0] < t + FRAME_MS),
                (t + FRAME_MS, True),
                (t + 2 * FRAME_MS, False),
            ]

    def _end(self, t: float) -> None:
        self.state = None
        self._timers = {}
        self._generators = {}
        self._generator_starts = {}
        self.sounds = {}
        self._set_screen([], t)

    def _enter(self, name: str, t: float, depth: int) -> None:
        if depth > _MAX_STEPS:
            raise RuntimeError("Too many transitions at once; the machine loops")
        state = self._states.get(name)
        if name == EXIT or state is None:
            self._say(
                t, "trial ends" if name == EXIT else f'trial ends: no state "{name}"'
            )
            self._end(t)
            return
        self.state = name
        self.entered_at = t
        self._timed_out = False
        self.visited.append(Visit(name, t))
        self._say(t, f"enter {name}")
        # All of the state's screen actions are one change of the screen.
        shown = self.shown
        for action in state.on_entry:
            if isinstance(action, ShowAction):
                stimulus = self._stimuli.get(action.show)
                if stimulus is not None and not isinstance(
                    stimulus, (WavStimulus, TonesStimulus)
                ):
                    shown = [*(n for n in shown if n != action.show), action.show]
            elif isinstance(action, HideAction):
                shown = [n for n in shown if n != action.hide]
            elif isinstance(action, ClearAction):
                shown = []
            elif isinstance(action, ResetAction):
                self.counters[action.reset] = 0
            elif isinstance(action, StopAction):
                self._timers.pop(action.stop, None)
                self._generators.pop(action.stop, None)
                self._generator_starts.pop(action.stop, None)
                self.sounds.pop(action.stop, None)
            elif isinstance(action, PlayAction):
                sound = self._stimuli.get(action.play)
                if isinstance(sound, (WavStimulus, TonesStimulus)):
                    self.sounds[sound.name] = t + sound.duration
            else:
                self._start(action.start, t)
        self._set_screen(shown, t)
        # Level events hold for inputs already at that level when the state is entered.
        levels = [
            f"{name}.{'high' if high else 'low'}" for name, high in self.inputs.items()
        ]
        self._fire(levels, t, depth + 1, quiet=True)

    def _start(self, name: str, t: float) -> None:
        for timer in self._machine.timers:
            if timer.name == name:
                self._timers[name] = t + amount_in(self.values, timer.time)
                break
        for generator in self._machine.generators:
            if generator.name == name:
                count = amount_in(self.values, generator.count)
                self._generator_starts[name] = t
                self._generators[name] = (
                    None
                    if count == 0
                    else t
                    + amount_in(self.values, generator.delay)
                    + amount_in(self.values, generator.period) * (count - 1)
                    + amount_in(self.values, generator.width)
                )
                break

    def _fire(
        self, events: list[str], t: float, depth: int, *, quiet: bool = False
    ) -> None:
        """Handle events that occur together: the first transition, in the order tried,
        that matches any of them is taken."""
        if self.state is None:
            return
        reached: list[str] = []
        if not quiet:
            for counter in self._machine.counters:
                if counter.event in events:
                    count = self.counters.get(counter.name, 0) + 1
                    self.counters[counter.name] = count
                    if count == amount_in(self.values, counter.limit):
                        reached.append(f"{counter.name}.reached")
        for holder in self._holders(self.state):
            transitions: list[Transition] = (
                self._states.get(holder) or self._groups[holder]
            ).transitions
            taken = next((t_ for t_ in transitions if t_.event in events), None)
            if taken is not None:
                target = target_in(self.values, taken.target)
                via = (
                    f" (${taken.target.param})"
                    if isinstance(taken.target, ParamRef)
                    else ""
                )
                self._say(t, f"{taken.event} → {target}{via}")
                self._enter(target, t, depth + 1)
                if reached:
                    self._fire(reached, t, depth + 1)
                return
        if not quiet:
            named = [e for e in events if not e.endswith((".high", ".low"))]
            self._say(t, f"{', '.join(named)} (no transition)")
        if reached:
            self._fire(reached, t, depth + 1)

    def _set_level(self, name: str, high: bool, t: float) -> None:
        if self.inputs.get(name) == high:
            return
        self.inputs[name] = high
        edge = f"{name}.{'rise' if high else 'fall'}"
        if self.state is None:
            self._say(t, f"{edge} (between trials)")
        else:
            self._fire([edge, f"{name}.{'high' if high else 'low'}"], t, 0)

    def _due(self) -> list[tuple[float, Callable[[], None]]]:
        """What will happen by itself, the earliest first."""
        due: list[tuple[float, Callable[[], None]]] = []
        state = self._states.get(self.state) if self.state is not None else None
        if state is not None and state.timeout is not None and not self._timed_out:
            due.append(
                (
                    self.entered_at + amount_in(self.values, state.timeout),
                    self._on_timeout,
                )
            )
        for name, at in self._timers.items():
            due.append((at, lambda name=name: self._on_done(self._timers, name)))
        for name, at in self.sounds.items():
            due.append((at, lambda name=name: self._on_done(self.sounds, name)))
        for name, at in self._generators.items():
            if at is not None:
                due.append(
                    (at, lambda name=name: self._on_done(self._generators, name))
                )
        if self._flashes:
            due.append((self._flashes[0][0], self._on_flash))
        # A stable sort: what falls due together is handled in the order listed.
        return sorted(due, key=lambda item: item[0])

    def _on_timeout(self) -> None:
        self._timed_out = True
        self._fire(["timeout"], self.now, 0)

    def _on_done(
        self, running: dict[str, float] | dict[str, float | None], name: str
    ) -> None:
        del running[name]
        if running is self._generators:
            del self._generator_starts[name]
        self._fire([f"{name}.done"], self.now, 0)

    def _on_flash(self) -> None:
        _, high = self._flashes.pop(0)
        self._set_level(PHOTODIODE, high, self.now)
