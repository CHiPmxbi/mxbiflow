"""The experiment configuration that cogmote sends to the rig.

cogmoteGO caches the device configuration from its heartbeat; the
``experiment`` key holds :class:`~mxbiflow.models.experiment.ExperimentConfig`
with each animal's CogMatrix name and RFID tags (cagelab/cogmote#344). The rig
never queries CogMatrix for animals.
"""

from collections.abc import Collection

from pymotego import Client

from ..core.config_store import ConfigStore
from ..core.path import get_applied_cogmote_config_path, get_config_session_path
from ..models.animal import AnimalConfig
from ..models.experiment import ExperimentAnimal, ExperimentConfig
from ..models.session import SessionConfig


class CogmoteConfigError(Exception):
    """The cogmote configuration cannot start a run; the message says why."""


def read_experiment_config(client: Client | None = None) -> ExperimentConfig | None:
    """Return the configured experiment, or ``None`` when none is configured.

    Raises the pymoteGO error when cogmoteGO is unreachable, and
    ``pydantic.ValidationError`` for a configuration mxbiflow cannot read.
    """
    config = (client if client is not None else Client()).get_config()
    experiment = config.get("experiment")
    if experiment is None:
        return None
    return ExperimentConfig.model_validate(experiment)


def session_config_from_experiment(
    experiment: ExperimentConfig,
    *,
    stages: Collection[str],
    previous: SessionConfig | None = None,
    applied: ExperimentConfig | None = None,
) -> SessionConfig:
    """Map the cogmote configuration to the session configuration of a run.

    An animal keeps its local progress (stage and level, from ``previous``)
    while cogmote still has the stage and level that were ``applied`` at the
    last start; an operator's change in cogmote replaces it.
    Raises :class:`CogmoteConfigError` for stages the experiment does not
    register.
    """
    names = [animal.name for animal in experiment.animals]
    if len(set(names)) != len(names):
        raise CogmoteConfigError(f"animal names must be unique: {', '.join(names)}")
    parameters = experiment.parameters
    unknown = sorted(
        {animal.stage for animal in experiment.animals}.union(
            s for s in (parameters.default_scene, parameters.fault_fallback) if s
        ).difference(stages)
    )
    if unknown:
        raise CogmoteConfigError(
            f"unknown stages {', '.join(unknown)}; "
            f"this experiment registers {', '.join(sorted(stages))}"
        )

    local = {a.cogmatrix_id: a for a in previous.animals} if previous else {}
    last = {a.id: a for a in applied.animals} if applied else {}

    def animal_config(animal: ExperimentAnimal) -> AnimalConfig:
        config = AnimalConfig(
            cogmatrix_id=animal.id,
            rfid_tags=animal.rfid_tags,
            name=animal.name,
            stage=animal.stage,
            level=animal.level,
        )
        before, progress = last.get(animal.id), local.get(animal.id)
        unchanged = before is not None and (before.stage, before.level) == (
            animal.stage,
            animal.level,
        )
        if unchanged and progress is not None and progress.stage in stages:
            return config.with_progress(stage=progress.stage, level=progress.level)
        return config

    return SessionConfig(
        experimenter=previous.experimenter if previous else "auto",
        reward_type=parameters.reward_type,
        send_email=parameters.send_email,
        note=parameters.note,
        default_scene=parameters.default_scene,
        fault_fallback=parameters.fault_fallback,
        hide_cursor=parameters.hide_cursor,
        fullscreen=parameters.fullscreen,
        animals=tuple(animal_config(animal) for animal in experiment.animals),
    )


def apply_cogmote_config(stages: Collection[str], client: Client | None = None) -> None:
    """Write the session configuration for a run from the cogmote configuration.

    ``init_gameloop`` then starts the run from it, as after the wizard.
    """
    try:
        experiment = read_experiment_config(client)
    except Exception as error:
        raise CogmoteConfigError(
            f"cannot read the cogmote configuration: {error}"
        ) from error
    if experiment is None:
        raise CogmoteConfigError(
            "no experiment is configured for this device in cogmote"
        )

    session_store = ConfigStore(get_config_session_path(), SessionConfig)
    applied_path = get_applied_cogmote_config_path()
    try:
        applied = ExperimentConfig.model_validate_json(
            applied_path.read_text(encoding="utf-8")
        )
    except OSError, ValueError:
        applied = None
    session_store.save(
        session_config_from_experiment(
            experiment, stages=stages, previous=session_store.value, applied=applied
        )
    )
    applied_path.parent.mkdir(parents=True, exist_ok=True)
    applied_path.write_text(experiment.model_dump_json(indent=2), encoding="utf-8")
