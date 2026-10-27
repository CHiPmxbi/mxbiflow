"""The ``trials`` broadcast event and its schema hint (CHiPmxbi/mxbiflow#206).

An event is the trial's context from mxbiflow at the top level and the
experiment's own record under ``record``. A record model's ``AnimalBaseInfo``
field repeats that context, so it is left out of the broadcast (it stays in the
saved record).

The hint for cogmote's live data table (cagelab/cogmote#432) is derived from
:class:`TrialEvent` and the record model: field ``title``, and ``unit``,
``decimals`` and :data:`COLUMN_MARKER` in ``json_schema_extra``::

    response_latency_ms: float | None = Field(
        None, title="Reaction time", json_schema_extra={"unit": "ms", "decimals": 0, **COLUMN}
    )
"""

import types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, Field, JsonValue
from pydantic.fields import FieldInfo

from .animal import AnimalBaseInfo

HINT_VERSION = 1

#: Marks a record field as one of the table's default columns.
COLUMN_MARKER = "x-mxbi-column"
COLUMN: dict[str, JsonValue] = {COLUMN_MARKER: True}

_RECORD = "record"


class TrialEvent(BaseModel):
    """One event of the ``trials`` broadcast, in column order."""

    trial_id: int = Field(title="Trial", json_schema_extra=COLUMN)
    animal: str = Field(title="Animal", json_schema_extra=COLUMN)
    stage: str = Field(title="Stage", json_schema_extra=COLUMN)
    level: int = Field(title="Level", json_schema_extra=COLUMN)
    correct: bool | None = Field(title="Correct", json_schema_extra=COLUMN)
    level_trial_id: int = Field(title="Level trial")
    animal_session_id: int = Field(title="Animal session")
    animal_session_trial_id: int = Field(title="Animal session trial")
    session_id: int = Field(title="Session")
    record: dict[str, JsonValue]


def split_record(
    record: BaseModel,
) -> tuple[AnimalBaseInfo | None, dict[str, JsonValue]]:
    """Split ``record`` into its ``AnimalBaseInfo``, if any, and the rest as JSON.

    The base info is the animal's state when the trial started, so it is the
    event's context rather than the state after settlement (a level up).
    """
    exclude = {
        name
        for name, field in type(record).model_fields.items()
        if _is_base_info(field.annotation)
    }
    base_info = next(
        (
            value
            for name in exclude
            if isinstance(value := getattr(record, name), AnimalBaseInfo)
        ),
        None,
    )
    return base_info, record.model_dump(mode="json", exclude=exclude)


def schema_hint(record_type: type[BaseModel] | None) -> dict[str, Any]:
    """Return the ``trials.schema`` hint for events whose record is ``record_type``."""
    columns: list[str] = []
    fields: dict[str, dict[str, Any]] = {}
    collapsed: list[str] = []
    _walk(TrialEvent, "", columns, fields, collapsed)
    if record_type is not None:
        _walk(record_type, f"{_RECORD}.", columns, fields, collapsed)
    return {
        "version": HINT_VERSION,
        "columns": columns,
        "fields": fields,
        "expanded": [_RECORD] if record_type is not None else [],
        "collapsed": collapsed,
    }


def _walk(
    model: type[BaseModel],
    prefix: str,
    columns: list[str],
    fields: dict[str, dict[str, Any]],
    collapsed: list[str],
) -> None:
    for name, field in model.model_fields.items():
        if _is_base_info(field.annotation):
            continue
        path = prefix + name
        extra = (
            field.json_schema_extra if isinstance(field.json_schema_extra, dict) else {}
        )
        if extra.get(COLUMN_MARKER):
            columns.append(path)
        if hint := _field_hint(field, extra):
            fields[path] = hint
        nested = _model(field.annotation)
        if nested is not None:
            if prefix:
                collapsed.append(path)
            _walk(nested, f"{path}.", columns, fields, collapsed)


def _field_hint(field: FieldInfo, extra: dict[str, Any]) -> dict[str, Any]:
    hint: dict[str, Any] = {}
    if field.title:
        hint["title"] = field.title
    for key in ("unit", "decimals"):
        if key in extra:
            hint[key] = extra[key]
    return hint


def _is_base_info(annotation: Any) -> bool:
    model = _model(annotation)
    return model is not None and issubclass(model, AnimalBaseInfo)


def _model(annotation: Any) -> type[BaseModel] | None:
    """The model an annotation holds as an object, unwrapping ``X | None``."""
    if get_origin(annotation) in (Union, types.UnionType):
        models = [_model(arg) for arg in get_args(annotation) if arg is not type(None)]
        return models[0] if len(models) == 1 else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None
