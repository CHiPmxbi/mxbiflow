"""The experiment configuration that cogmote sends to the rig.

cogmoteGO caches the device configuration from its heartbeat; the
``experiment`` key holds :class:`~mxbiflow.models.experiment.ExperimentConfig`
with each animal's CogMatrix name and RFID tags (cagelab/cogmote#344). The rig
never queries CogMatrix for animals.
"""

from pymotego import Client

from ..models.experiment import ExperimentConfig


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
