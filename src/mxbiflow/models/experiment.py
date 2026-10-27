"""Experiment configuration that operators edit in cogmote (cagelab/cogmote#344).

cogmote generates its form from :func:`experiment_config_schema`, looks up the
chosen animals in CogMatrix, and sends the result to the rig in the device
configuration, where mxbiflow reads it with ``pymotego.Client().get_config()``.
Fields marked ``readOnly`` are filled by cogmote, not by the operator,
``x-cogmatrix`` marks CogMatrix IDs that cogmote offers pickers for and checks,
and ``x-mxbi-stages`` marks the stage configurations that cogmote's stage editor
writes (:mod:`mxbiflow.models.stage_config`).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .reward import RewardEnum

_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class CogMatrixRef(BaseModel):
    """A CogMatrix record the operator picks in cogmote; ``x-cogmatrix`` names its type."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, description="CogMatrix ID")
    name: str = Field(
        default="",
        description="CogMatrix name; set by cogmote",
        json_schema_extra={"readOnly": True},
    )


class ExperimentAnimal(BaseModel):
    model_config = ConfigDict(frozen=True, title="Animal")

    id: str = Field(
        min_length=1,
        title="Animal",
        description="CogMatrix animal ID",
        json_schema_extra={"x-cogmatrix": "animal"},
    )
    name: str = Field(
        default="",
        description="CogMatrix display name; set by cogmote",
        json_schema_extra={"readOnly": True},
    )
    rfid_tags: tuple[str, ...] = Field(
        default=(),
        title="RFID tags",
        description="Current CogMatrix rfid identifiers; set by cogmote",
        json_schema_extra={"readOnly": True},
    )
    stage: str = Field(
        min_length=1,
        max_length=200,
        description="Stage the animal trains in; must be registered by the experiment",
    )
    level: int = Field(default=0, ge=0, description="Level within the stage")


class ExperimentParameters(BaseModel):
    model_config = ConfigDict(frozen=True, title="Parameters")

    reward_type: RewardEnum = Field(
        default=RewardEnum.AGUM_ONE_FIFTH, title="Reward type"
    )
    send_email: bool = Field(default=False, description="Send the daily report")
    note: str = Field(default="", max_length=1000)
    default_scene: str = Field(
        default="",
        max_length=200,
        description="Scene shown when no animal is present; empty uses idle",
    )
    fault_fallback: str = Field(
        default="",
        max_length=200,
        description="Scene shown on a detector fault; empty uses idle",
    )
    hide_cursor: bool = True
    fullscreen: bool = True


class RecordingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, title="Recording")

    record_camera: bool = Field(
        default=False,
        title="Record the camera",
        description="Record the rig camera during sessions and upload it to CogMatrix",
    )
    capture_latency_ms: int = Field(
        default=0,
        ge=0,
        le=1000,
        title="Capture latency (ms)",
        description="Camera-to-MediaMTX delay that the trial subtitles correct for",
    )


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, title="MXBI experiment")

    experiment: str = Field(
        default="",
        max_length=200,
        description="Experiment name for operators; the rig runs its installed experiment",
    )
    protocol: CogMatrixRef = Field(
        title="Protocol",
        description="CogMatrix protocol of the sessions",
        json_schema_extra={"x-cogmatrix": "protocol"},
    )
    repository: CogMatrixRef = Field(
        title="Data repository",
        description="CogMatrix storage repository for the results",
        json_schema_extra={"x-cogmatrix": "repository"},
    )
    animals: tuple[ExperimentAnimal, ...] = Field(
        min_length=1,
        description="The cage's animals, fixed for the run; animal IDs are unique",
    )
    parameters: ExperimentParameters = Field(default_factory=ExperimentParameters)
    recording: RecordingConfig = Field(default_factory=RecordingConfig)
    stages: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        title="Stage configurations",
        description=(
            "Stage name to its config.json document: the default and per-animal "
            "overrides by animal name; a stage without one uses its template"
        ),
        json_schema_extra={"x-mxbi-stages": True},
    )

    @model_validator(mode="after")
    def _validate_unique_animals(self) -> ExperimentConfig:
        ids = [animal.id for animal in self.animals]
        if len(ids) != len(set(ids)):
            raise ValueError("animal IDs must be unique")
        return self


def experiment_config_schema() -> dict[str, Any]:
    """Return the JSON Schema (2020-12) of :class:`ExperimentConfig`."""
    return inlined_json_schema(ExperimentConfig)


def inlined_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return the JSON Schema (2020-12) of ``model``.

    References are inlined, so form generators need no ``$ref`` resolution.
    """
    schema = model.model_json_schema()
    defs: dict[str, Any] = schema.pop("$defs", {})
    return {"$schema": _SCHEMA_DIALECT, **_inline_refs(schema, defs)}


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    inlined = {key: _inline_refs(value, defs) for key, value in node.items()}
    discriminator = inlined.get("discriminator")
    if isinstance(discriminator, dict) and "mapping" in discriminator:
        # The mapping points into the removed $defs; the oneOf options remain.
        inlined["discriminator"] = {
            k: v for k, v in discriminator.items() if k != "mapping"
        }
    ref = inlined.pop("$ref", None)
    if ref is None:
        return inlined
    target = _inline_refs(defs[ref.removeprefix("#/$defs/")], defs)
    return {**target, **inlined}
