"""What is wrong with an experiment's levels: cogforge's ``validateExperiment``.

cogforge refuses these while an experiment is edited; a file written by hand or by
``StageBuilder`` has not been through it, and each of them would otherwise go wrong
silently in a trial (one value overriding another, a stimulus never shown).
"""

from .models import (
    Experiment,
    HideAction,
    Machine,
    Order,
    ParamRef,
    PlayAction,
    ShowAction,
    Stage,
    StopAction,
    TonesStimulus,
    Value1,
    Value2,
    WavStimulus,
)
from .runner import EXIT

type Fixed = float | str


def stimulus_uses(machine: Machine) -> dict[str, set[str]]:
    """How each stimulus parameter is used: on the ``screen``, as a ``sound``."""
    uses: dict[str, set[str]] = {}
    for state in machine.states:
        for action in state.on_entry:
            if isinstance(action, (ShowAction, HideAction)):
                ref, use = (
                    action.show if isinstance(action, ShowAction) else action.hide,
                    "screen",
                )
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


def stage_problems(stage: Stage) -> list[str]:
    """What is wrong with the stage's stimulus parameters, levels and factors."""
    machine = stage.machine
    problems: list[str] = []
    types = {p.name: p.type for p in machine.parameters}
    states = {s.name for s in machine.states}
    uses = stimulus_uses(machine)

    for param in machine.parameters:
        if param.type != "stimulus":
            continue
        if len(uses.get(param.name, ())) == 2:
            problems.append(
                f"{stage.name}: the stimulus parameter {param.name} is both shown "
                "and played"
            )
        found = _stimulus_problem(machine, param.name, param.default)
        if found:
            problems.append(f"{stage.name}: {found}")
    for name in uses:
        if types.get(name) != "stimulus":
            problems.append(f"{stage.name}: {name} is not a stimulus parameter")

    def check_fixed(where: str, name: str, value: Fixed) -> None:
        kind = types.get(name)
        if kind is None:
            problems.append(f"{where}: no parameter {name}")
        elif kind == "state":
            if not isinstance(value, str):
                problems.append(f"{where}: {name} needs a state")
            elif value != EXIT and value not in states:
                problems.append(f'{where}: {name}: no state "{value}"')
        elif kind == "stimulus":
            if not isinstance(value, str):
                problems.append(f"{where}: {name} needs a stimulus")
            else:
                found = _stimulus_problem(machine, name, value)
                if found:
                    problems.append(f"{where}: {found}")
        elif isinstance(value, str):
            problems.append(f"{where}: {name} needs a number")

    level_names: set[str] = set()
    for level in stage.levels:
        where = f"{stage.name} / {level.name}"
        if level.name in level_names:
            problems.append(f"{where}: the level's name is used twice")
        level_names.add(level.name)
        for name, value in level.values.items():
            if isinstance(value, Value2):
                for item in value.choice:
                    check_fixed(where, name, item)
            elif isinstance(value, Value1):
                kind = types.get(name)
                if kind is None:
                    problems.append(f"{where}: no parameter {name}")
                elif kind in ("state", "stimulus"):
                    problems.append(f"{where}: {name} needs a {kind}, not a range")
                elif value.uniform[0] > value.uniform[1]:
                    problems.append(f"{where}: the range of {name} is backwards")
            else:
                check_fixed(where, name, value)
        # Who sets each parameter: the level itself or a factor. Two setters would
        # silently override each other.
        set_by = dict.fromkeys(level.values, level.name)
        factor_names: set[str] = set()
        for factor in level.factors:
            at = f"{where} / {factor.name}"
            if factor.name in factor_names:
                problems.append(f"{at}: the factor's name is used twice")
            factor_names.add(factor.name)
            if not factor.rows:
                problems.append(f"{at}: the factor has no rows")
            elif factor.order is Order.random and all(
                row.weight == 0 for row in factor.rows
            ):
                problems.append(f"{at}: every row's weight is 0")
            row_names: set[str] = set()
            set_here: dict[str, None] = {}
            for row in factor.rows:
                if row.name in row_names:
                    problems.append(f'{at}: the row name "{row.name}" is used twice')
                row_names.add(row.name)
                for name, value in row.values.items():
                    check_fixed(f"{at} / {row.name}", name, value)
                    set_here[name] = None
            for name in set_here:
                if name in set_by:
                    problems.append(
                        f"{at}: {name} is set twice, by {set_by[name]} and by "
                        f"{factor.name}"
                    )
                else:
                    set_by[name] = factor.name
    return problems


def check_experiment(experiment: Experiment) -> None:
    """Raise ``ValueError`` naming everything wrong with the experiment's levels."""
    problems = [p for stage in experiment.stages for p in stage_problems(stage)]
    for animal in experiment.animals:
        for stage in experiment.stages:
            types = {p.name: p.type for p in stage.machine.parameters}
            for name, value in animal.values.items():
                if name in types and (
                    types[name] in ("state", "stimulus")
                ) != isinstance(value, str):
                    problems.append(
                        f"{animal.name}: {name} is of the wrong kind for {stage.name}"
                    )
    if problems:
        raise ValueError("the experiment cannot run: " + "; ".join(problems))
