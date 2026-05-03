"""
Port and parameter primitives used by NodeSpecs.

Kept intentionally small. The frontend's config inspector consumes
`params`; the validator + dag_runner consume `input_ports` and
`output_ports`. New fields are additive — never remove a field a node
yaml depends on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PortType(str, Enum):
    DATAFRAME = "dataframe"   # list[dict] — the row plane
    SCALAR = "scalar"
    TEXT = "text"
    OBJECT = "object"
    ANY = "any"


class ParamType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    CODE = "code"
    JSON = "json"
    INPUT_REF = "input_ref"
    COLUMN_REF = "column_ref"
    COLUMN_LIST = "column_list"
    EXPRESSION = "expression"


class Widget(str, Enum):
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    CODE_EDITOR = "code_editor"
    JSON_EDITOR = "json_editor"
    SWITCH = "switch"


@dataclass(frozen=True)
class PortSpec:
    name: str
    type: PortType
    description: str = ""
    optional: bool = False
    # Where the handler stores this output (informational, used by validator).
    store_at: str = ""


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: ParamType
    description: str = ""
    required: bool = False
    default: Any = None
    enum: tuple[str, ...] = field(default_factory=tuple)
    widget: Widget | None = None
    placeholder: str = ""
    visible_if: dict[str, Any] | None = None
  