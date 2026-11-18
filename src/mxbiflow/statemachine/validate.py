"""What is wrong with a machine's stimulus parameters, and with a trial's values.

cogforge refuses these while a machine is edited (``validate`` and ``valueProblems`` in
its ``src/model/validate.ts``); a machine written in Python and the values a stage
gives a trial have not been through it, and each would otherwise go wrong silently in
a trial (a stimulus never shown, a value that is ignored).
"""

from collections.abc import Mapping

from .models import (
    HideAction,
    Machine,
    ParamRef,
    PlayAction,
    ShowAction,
    StopAction,
    TonesStimulus,
    WavStimulus,
)
from .runner import EXIT


def stimulus_uses(machine: Machine) -> dict[str, set[str]]:
    """How each stimulus parameter is used: on the ``screen``, as a ``sound``."""
    uses: dict[str, set[str]] = {}
    for state in machine.states:
        for action in state.on_entry:
            if isinstance(action, ShowAction):
                ref, use = action.show, "screen"
            elif isinstance(action, HideAction):
                ref, use = action.hide, "screen"
            elif isinstance(action, PlayAction):
                ref, use = action.play, "sound"
            elif isinstance(action, StopAction):
                ref, use = action.stop, "sound"
            else:
                continue
            if isinstance(ref, ParamRef):
                uses.setdefault(ref.param, set()).add(use)
    return uses


def _stimulus_problem(machine: Machine, param: str, value: str) -> str | None:
    """Why a stimulus parameter cannot take this value, if it cannot."""
    stimulus = next((s for s in machine.stimuli if s.name == value), None)
    is_sound = isinstance(stimulus, (WavStimulus, TonesStimulus))
    use = stimulus_uses(machine).get(param, set())
    if "screen" in use and (stimulus is None or is_sound):
        return f'{param}: "{value}" is not a stimulus on the screen'
    if "sound" in use and not is_sound:
        return f'{param}: "{value}" is not a sound'
    if stimulus is None:
        return f'{param}: no stimulus "{value}"'
    return None


def machine_problems(machine: Machine) -> list[str]:
    """What is wrong with the machine's stimulus parameters."""
    problems: list[str] = []
    types = {p.name: p.type for p in machine.parameters}
    uses = stimulus_uses(machine)
    for param in machine.parameters:
        if param.type != "stimulus":
            continue
        if len(uses.get(param.name, ())) == 2:
            problems.append(
                f"the stimulus parameter {param.name} is both shown and played"
            )
        found = _stimulus_problem(machine, param.name, param.default)
        if found:
            problems.append(found)
    problems += [
        f"{name} is not a stimulus parameter"
        for name in uses
        if types.get(name) != "stimulus"
    ]
    return problems


def value_problems(machine: Machine, values: Mapping[str, float | str]) -> list[str]:
    """What is wrong with the values a trial is given.

    Each must name a parameter and be of its kind: a number, a state's name or the exit
    for a ``state`` parameter, a stimulus of the right kind for a ``stimulus`` one.
    """
    problems: list[str] = []
    types = {p.name: p.type for p in machine.parameters}
    states = {state.name for state in machine.states}
    for name, value in values.items():
        kind = types.get(name)
        if kind is None:
            problems.append(f"no parameter {name}")
        elif kind == "state":
            if not isinstance(value, str):
                problems.append(f"{name} needs a state")
            elif value != EXIT and value not in states:
                problems.append(f'{name}: no state "{value}"')
        elif kind == "stimulus":
            if not isinstance(value, str):
                problems.append(f"{name} needs a stimulus")
            else:
                found = _stimulus_problem(machine, name, value)
                if found:
                    problems.append(found)
        elif isinstance(value, (str, bool)):
            problems.append(f"{name} needs a number")
    return problems
