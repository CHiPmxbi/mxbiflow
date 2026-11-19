"""Runs one trial of a machine, as cogforge's ``src/model/simulate.ts`` does.

A port with the same semantics, so both pass cogforge's conformance cases, by the rules
of the format: events are handled one at a time in order of their time; a state's
transitions are tried before its groups' from the innermost outwards; a transition runs
the state's ``onExit``, the ``onExit`` of the groups it leaves (inside out), its own
actions, the ``onEntry`` of the groups it enters (outside in) and the state's
``onEntry``; level events hold for inputs already at that level when a state is
entered. An error ends the trial at once with outputs low. Times are milliseconds from
the start of the trial. Nothing here touches hardware: the caller reports inputs and
touches, lets time run with :meth:`Trial.advance`, and reads what to show, play and
drive from the trial.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .models import (
    After,
    Amount1,
    BackgroundStimulus,
    CancelAction,
    CircleStimulus,
    ClearAction,
    CrossStimulus,
    Duration,
    HideAction,
    HighAction,
    ImageStimulus,
    LowAction,
    Machine,
    ParamRef,
    PlayAction,
    RectStimulus,
    ResetAction,
    ShowAction,
    Size,
    StartAction,
    State,
    StopAction,
    TextStimulus,
    TonesStimulus,
    WavStimulus,
)

EXIT = "exit"
# The input that follows the screen when the photodiode is simulated.
PHOTODIODE = "screen_on"
FRAME_MS = 17
# State entries at one instant before the trial is ended as a loop.
MAX_ENTRIES = 64
_MAX_STEPS = 10000

type Values = dict[str, float | str]
type Amount = Amount1 | After | Duration | ParamRef
type Action = (
    HighAction
    | LowAction
    | CancelAction
    | StartAction
    | StopAction
    | ResetAction
    | ShowAction
    | HideAction
    | ClearAction
    | PlayAction
)
type Sound = WavStimulus | TonesStimulus
type VisualStimulus = (
    ImageStimulus | CircleStimulus | RectStimulus | CrossStimulus | TextStimulus
)


@dataclass(frozen=True)
class Visit:
    state: str
    t: float


@dataclass(frozen=True)
class LogEntry:
    t: float
    text: str


@dataclass(frozen=True)
class Edge:
    """A change of an output."""

    t: float
    output: str
    high: bool


class TrialError(StrEnum):
    """What ends a trial as an error."""

    LOOP = "loop"
    TIMER_RUNNING = "timer_running"
    EDGE_PAST = "edge_past"
    NO_STATE = "no_state"


def default_values(machine: Machine) -> Values:
    return {parameter.name: parameter.default for parameter in machine.parameters}


def amount_in(values: Values, amount: Amount) -> float:
    if not isinstance(amount, ParamRef):
        return amount.root
    found = values.get(amount.param)
    return found if isinstance(found, (int, float)) else 0


def target_in(values: Values, target: ParamRef | str) -> str:
    if isinstance(target, str):
        return target
    found = values.get(target.param)
    return found if isinstance(found, str) else EXIT


def stimulus_in(values: Values, stimulus: ParamRef | str) -> str:
    """The stimulus an action names with this trial's values."""
    if isinstance(stimulus, str):
        return stimulus
    found = values.get(stimulus.param)
    return found if isinstance(found, str) else ""


def duration_of(sound: Sound, values: Values) -> float:
    """A sound's length with this trial's values."""
    if isinstance(sound, WavStimulus):
        return sound.duration
    return amount_in(values, sound.duration)


@dataclass(frozen=True)
class Place:
    """A visual stimulus on a screen: its centre and size in pixels."""

    x: float
    y: float
    width: float
    height: float


def place_of(
    stimulus: VisualStimulus, values: Values, screen: tuple[float, float]
) -> Place:
    """Where the stimulus lands on a screen of this size with this trial's values.

    Its centre is a fraction of the screen; a ``fraction`` size is of the screen's
    width, for the width and the height.
    """
    width, height = screen
    scale = 1 if stimulus.size is Size.px else width
    return Place(
        amount_in(values, stimulus.x) * width,
        amount_in(values, stimulus.y) * height,
        stimulus.width * scale,
        stimulus.height * scale,
    )


class Trial:
    """One trial of ``machine`` with this trial's parameter ``values``.

    ``inputs`` are the input levels when the trial starts. With ``photodiode`` an input
    called ``screen_on`` is simulated: it flashes for one frame, one frame after every
    change of the screen. A rig with a real photodiode reports it as any other input.
    ``screen`` is the size in pixels of the screen touches are on; the machine's own
    is only cogforge's reference.
    """

    def __init__(
        self,
        machine: Machine,
        inputs: Mapping[str, bool] | None = None,
        t: float = 0,
        values: Values | None = None,
        *,
        photodiode: bool = True,
        screen: tuple[float, float] | None = None,
    ) -> None:
        self._machine = machine
        self._screen = screen or (machine.screen.width, machine.screen.height)
        self._states = {state.name: state for state in machine.states}
        self._groups = {group.name: group for group in machine.groups}
        self._stimuli = {stimulus.name: stimulus for stimulus in machine.stimuli}
        self._timer_times = {timer.name: timer.time for timer in machine.timers}
        self._photodiode = photodiode and PHOTODIODE in machine.channels.inputs

        #: The current state; ``None`` once the trial has ended.
        self.state: str | None = None
        #: Why the trial ended, if by an error.
        self.error: TrialError | None = None
        #: What the error was about, in words.
        self.error_detail = ""
        self.values: Values = default_values(machine) if values is None else values
        #: Every state entered, with its time.
        self.visited: list[Visit] = []
        self.now = t
        self.inputs: dict[str, bool] = {
            name: bool(inputs and inputs.get(name)) for name in machine.channels.inputs
        }
        #: The level of every output.
        self.outputs: dict[str, bool] = dict.fromkeys(machine.channels.outputs, False)
        #: Every change of an output so far.
        self.changes: list[Edge] = []
        #: Timed edges still to come, in order of their time.
        self.queue: list[Edge] = []
        #: Stimuli on the screen, in the order they were shown (the last on top).
        self.shown: list[str] = []
        #: Sounds playing: when they end.
        self.sounds: dict[str, float] = {}
        self.counters: dict[str, int] = {}
        self.log: list[LogEntry] = []

        # Running timers: when they are done.
        self._timers: dict[str, float] = {}
        # The photodiode's coming changes.
        self._flashes: list[tuple[float, bool]] = []
        # State entries at the instant ``_entries_at``.
        self._entries = 0
        self._entries_at = t

        self._say(t, "trial starts")
        self._go(machine.start, [], t)

    # ---- what the host reads -------------------------------------------------

    def high(self) -> set[str]:
        """The outputs that are high."""
        return {output for output, high in self.outputs.items() if high}

    def stimulus_at(self, x: float, y: float) -> str | None:
        """The visual stimulus on top at a point of the screen, or ``None``."""
        for name in reversed(self.shown):
            stimulus = self._stimuli.get(name)
            if stimulus is None or isinstance(
                stimulus, (BackgroundStimulus, WavStimulus, TonesStimulus)
            ):
                continue
            place = place_of(stimulus, self.values, self._screen)
            if (
                abs(x - place.x) <= place.width / 2
                and abs(y - place.y) <= place.height / 2
            ):
                return name
        return None

    # ---- what the host reports -----------------------------------------------

    def advance(self, t: float) -> None:
        """Let time run to ``t``, handling everything that falls due, in order.

        At the same time an output's edge comes before an event.
        """
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
        """The animal touches the screen at ``(x, y)`` pixels."""
        self.advance(t)
        if self.state is None:
            return
        self._fire([f"{self.stimulus_at(x, y) or 'screen'}.touch"], t)

    def host(self, name: str, t: float) -> None:
        """The host sends the event ``host.<name>``; its time is when it is taken."""
        self.advance(t)
        self._fire([f"host.{name}"], t)

    def stop(self, t: float) -> None:
        """The host ends the trial."""
        self.advance(t)
        if self.state is not None:
            self._say(t, "trial stopped")
            self._end(t)

    # ---- the machine ---------------------------------------------------------

    def _say(self, t: float, text: str) -> None:
        self.log.append(LogEntry(t, text))

    def _groups_of(self, state: str | None) -> list[str]:
        """The state's groups from the innermost outwards."""
        chain: list[str] = []
        found = self._states.get(state) if state is not None else None
        group = found.group if found else None
        while group is not None and group not in chain:
            chain.append(group)
            parent = self._groups.get(group)
            group = parent.group if parent else None
        return chain

    def _holder(self, name: str) -> State | None:
        return self._states.get(name) or self._groups.get(name)

    def _set_output(self, output: str, high: bool, t: float) -> None:
        if self.outputs.get(output, False) == high:
            return
        self.outputs[output] = high
        self.changes.append(Edge(t, output, high))
        self._say(t, f"{output} {'high' if high else 'low'}")

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
        """The trial is over: outputs low, nothing left running or queued."""
        self.state = None
        self._timers = {}
        self.queue = []
        self.sounds = {}
        for output in self.outputs:
            self._set_output(output, False, t)
        self._set_screen([], t)

    def _fail(self, t: float, error: TrialError, detail: str) -> None:
        if self.state is None and self.error is not None:
            return
        self.error = error
        self.error_detail = detail
        self._say(t, f"error: {detail}; trial ends")
        self._end(t)

    def _find(self, ref: ParamRef | str, *, visual: bool, t: float) -> str | None:
        """The stimulus of the right kind an action names, or ``None`` and a log line.

        A stimulus named by a parameter that names none is said, not skipped silently.
        """
        name = stimulus_in(self.values, ref)
        stimulus = self._stimuli.get(name)
        is_sound = isinstance(stimulus, (WavStimulus, TonesStimulus))
        if stimulus is not None and is_sound != visual:
            return name
        param = f" (${ref.param})" if isinstance(ref, ParamRef) else ""
        self._say(t, f'no stimulus "{name}"{param}')
        return None

    def _run(self, actions: Sequence[Action], t: float) -> None:
        """Run one list of actions; an error ends the trial and the rest is not run."""
        # All of the list's screen actions are one change of the screen.
        shown = self.shown
        for action in actions:
            if self.error is not None:
                return
            if isinstance(action, (HighAction, LowAction)):
                high = isinstance(action, HighAction)
                output = action.high if isinstance(action, HighAction) else action.low
                if action.after is None:
                    self._set_output(output, high, t)
                    continue
                at = t + amount_in(self.values, action.after)
                if at <= t:
                    self._fail(
                        t,
                        TrialError.EDGE_PAST,
                        f"{output}: the time of a timed edge has passed",
                    )
                    return
                # After the edges already queued for the same time.
                index = next(
                    (i for i, edge in enumerate(self.queue) if edge.t > at),
                    len(self.queue),
                )
                self.queue.insert(index, Edge(at, output, high))
            elif isinstance(action, CancelAction):
                self.queue = [e for e in self.queue if e.output != action.cancel]
            elif isinstance(action, ShowAction):
                found = self._find(action.show, visual=True, t=t)
                if found is not None:
                    shown = [*(n for n in shown if n != found), found]
            elif isinstance(action, HideAction):
                found = self._find(action.hide, visual=True, t=t)
                if found is not None:
                    shown = [n for n in shown if n != found]
            elif isinstance(action, ClearAction):
                shown = []
            elif isinstance(action, ResetAction):
                self.counters[action.reset] = 0
            elif isinstance(action, StopAction):
                found = stimulus_in(self.values, action.stop)
                self._timers.pop(found, None)
                self.sounds.pop(found, None)
            elif isinstance(action, PlayAction):
                found = self._find(action.play, visual=False, t=t)
                if found is None:
                    continue
                sound = self._stimuli[found]
                assert isinstance(sound, (WavStimulus, TonesStimulus))
                # A tone drawn with no length would never end.
                if isinstance(sound, TonesStimulus) and any(
                    amount_in(self.values, tone.duration) <= 0 for tone in sound.tones
                ):
                    self._say(t, f"{found}: a tone's duration is not positive")
                else:
                    self.sounds[found] = t + duration_of(sound, self.values)
            else:
                time = self._timer_times.get(action.start)
                if time is None:
                    continue
                if action.start in self._timers:
                    self._fail(
                        t,
                        TrialError.TIMER_RUNNING,
                        f"start {action.start}: the timer is running",
                    )
                    return
                self._timers[action.start] = t + amount_in(self.values, time)
        if self.state is not None or self.error is None:
            self._set_screen(shown, t)

    def _go(self, target: str, actions: Sequence[Action], t: float) -> None:
        """Leave the current state (none at the start) for ``target``."""
        left = self._groups_of(self.state)
        state = self._states.get(target)
        entered = self._groups_of(target) if state is not None else []
        lists: list[Sequence[Action]] = []
        if self.state is not None:
            current = self._holder(self.state)
            lists.append(current.on_exit if current else [])
        for group in left:
            if group not in entered:
                holder = self._holder(group)
                lists.append(holder.on_exit if holder else [])
        lists.append(actions)
        for actions_ in lists:
            self._run(actions_, t)
            if self.error is not None:
                return
        if target == EXIT:
            self._say(t, "trial ends")
            self._end(t)
            return
        if state is None:
            self._fail(t, TrialError.NO_STATE, f'no state "{target}"')
            return
        if t > self._entries_at:
            self._entries = 0
        self._entries_at = t
        self._entries += 1
        if self._entries > MAX_ENTRIES:
            self._fail(
                t,
                TrialError.LOOP,
                f"more than {MAX_ENTRIES} state entries at one instant",
            )
            return
        self.state = target
        self.visited.append(Visit(target, t))
        self._say(t, f"enter {target}")
        entries: list[Sequence[Action]] = []
        for group in reversed(entered):
            if group not in left:
                holder = self._holder(group)
                entries.append(holder.on_entry if holder else [])
        entries.append(state.on_entry)
        for actions_ in entries:
            self._run(actions_, t)
            if self.error is not None:
                return
        # Level events hold for inputs already at that level when the state is entered.
        levels = [
            f"{name}.{'high' if high else 'low'}" for name, high in self.inputs.items()
        ]
        self._fire(levels, t, quiet=True)

    def _fire(self, events: list[str], t: float, *, quiet: bool = False) -> None:
        """Handle one event under each of its names: the first transition, in the order
        tried, that names it is taken. A counter's ``reached`` follows as an event of
        its own, in the state the machine is then in."""
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
        taken = None
        for name in (self.state, *self._groups_of(self.state)):
            holder = self._holder(name)
            transitions = holder.transitions if holder else []
            taken = next((t_ for t_ in transitions if t_.event in events), None)
            if taken is not None:
                break
        if taken is not None and taken.target is None:
            self._say(t, taken.event)
            self._run(taken.actions, t)
        elif taken is not None and taken.target is not None:
            target = target_in(self.values, taken.target)
            via = (
                f" (${taken.target.param})"
                if isinstance(taken.target, ParamRef)
                else ""
            )
            self._say(t, f"{taken.event} → {target}{via}")
            self._go(target, taken.actions, t)
        elif not quiet:
            named = [e for e in events if not e.endswith((".high", ".low"))]
            self._say(t, f"{', '.join(named)} (no transition)")
        for event in reached:
            self._fire([event], t)

    def _set_level(self, name: str, high: bool, t: float) -> None:
        if self.inputs.get(name) == high:
            return
        self.inputs[name] = high
        edge = f"{name}.{'rise' if high else 'fall'}"
        if self.state is None:
            self._say(t, f"{edge} (between trials)")
        else:
            self._fire([edge, f"{name}.{'high' if high else 'low'}"], t)

    def _due(self) -> list[tuple[float, Callable[[], None]]]:
        """What will happen by itself, the earliest first."""
        due: list[tuple[float, Callable[[], None]]] = []
        if self.queue:
            due.append((self.queue[0].t, self._on_edge))
        for name, at in self._timers.items():
            due.append((at, lambda name=name: self._on_done(self._timers, name)))
        for name, at in self.sounds.items():
            due.append((at, lambda name=name: self._on_done(self.sounds, name)))
        if self._flashes:
            due.append((self._flashes[0][0], self._on_flash))
        # A stable sort: what falls due together is handled in the order listed.
        return sorted(due, key=lambda item: item[0])

    def _on_edge(self) -> None:
        edge = self.queue.pop(0)
        self._set_output(edge.output, edge.high, self.now)

    def _on_done(self, running: dict[str, float], name: str) -> None:
        del running[name]
        self._fire([f"{name}.done"], self.now)

    def _on_flash(self) -> None:
        _, high = self._flashes.pop(0)
        self._set_level(PHOTODIODE, high, self.now)
