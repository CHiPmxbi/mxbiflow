"""Stage configurations: fixed fields plus a level table (CHiPmxbi/mxbiflow#201).

A stage's ``config.json`` maps ``"default"`` to the stage configuration and
animal names to their overrides: only the fields that differ from the default,
merged over it before pydantic validates the result. cogmote's stage editor
(cagelab/cogmote#427) generates its form from the stage schema in the manifest,
where ``x-mxbi-levels`` marks the level table, and fields carry ``title``,
``description`` and ``unit`` metadata.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, WithJsonSchema

# Level IDs are JSON object keys, so the schema describes them as digit strings.
type LevelID = Annotated[
    int, Field(ge=1), WithJsonSchema({"type": "string", "pattern": "^[1-9][0-9]*$"})
]

DEFAULT_KEY = "default"
LEVELS_MARKER = "x-mxbi-levels"


class StageConfig[LevelT: BaseModel](BaseModel):
    """Base of a stage's configuration: subclasses add the fixed fields."""

    levels: dict[LevelID, LevelT] = Field(
        title="Levels",
        description="One row per level, difficulty increasing with the level",
        json_schema_extra={LEVELS_MARKER: True},
    )

    @classmethod
    def for_animal(cls, document: Mapping[str, Any], animal: str) -> Self:
        """Validate the default of ``document`` with ``animal``'s overrides merged over it."""
        if DEFAULT_KEY not in document:
            raise ValueError(f"the stage configuration has no {DEFAULT_KEY!r} entry")
        override = document.get(animal) or {}
        return cls.model_validate(merge_overrides(document[DEFAULT_KEY], override))


def merge_overrides(
    default: Mapping[str, Any], override: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge ``override`` over ``default``, recursing into objects such as the level table."""
    merged = dict(default)
    for key, value in override.items():
        base = merged.get(key)
        if isinstance(base, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_overrides(base, value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged
