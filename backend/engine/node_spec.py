"""
NodeSpec dataclass + the two factories every node module uses.

Each node module declares ONE of:

    NODE_SPEC = _spec(...)                  # legacy / inline
    NODE_SPEC = _spec_from_yaml(YAML, fn)   # preferred — YAML drives metadata

Both produce an identical `NodeSpec`. The registry auto-discovers them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from .context import RunContext
from .ports import ParamSpec, ParamType, PortSpec, PortType, Widget


# Handlers are sync. We keep this simple; async I/O is run via asyncio.to_thread
# inside the dag_runner if a node ever needs it (http, agent).
Handler = Callable[[dict, RunContext, dict[str, Any]], dict[str, Any]]
"""Signature: handler(node_dict, ctx, incoming_outputs) -> output_dict.

`incoming_outputs` maps upstream node id -> that node's output dict, exactly
the same shape the TS engine used. Handlers may mutate `ctx` for cross-node
state and MUST return the JSON-serialisable output for THIS node."""


@dataclass(frozen=True)
class NodeSpec:
    type_id: str
    description: str
    handler: Handler
    ui: dict[str, Any] = field(default_factory=dict)
    input_ports: tuple[PortSpec, ...] = field(default_factory=tuple)
    output_ports: tuple[PortSpec, ...] = field(default_factory=tuple)
    params: tuple[ParamSpec, ...] = field(default_factory=tuple)
    semantics_requires: tuple[str, ...] = field(default_factory=tuple)

    @property
    def contract(self) -> dict[str, Any]:
        """JSON-friendly view used by /contracts and Copilot prompts."""
        return {
            "type_id": self.type_id,
            "description": self.description,
            "ui": self.ui,
            "input_ports": [_port_to_dict(p) for p in self.input_ports],
            "output_ports": [_port_to_dict(p) for p in self.output_ports],
            "params": [_param_to_dict(p) for p in self.params],
            "semantics_requires": list(self.semantics_requires),
        }


def _port_to_dict(p: PortSpec) -> dict[str, Any]:
    return {
        "name": p.name,
        "type": p.type.value,
        "description": p.description,
        "optional": p.optional,
        "store_at": p.store_at,
    }


def _param_to_dict(p: ParamSpec) -> dict[str, Any]:
    return {
        "name": p.name,
        "type": p.type.value,
        "description": p.description,
        "required": p.required,
        "default": p.default,
        "enum": list(p.enum),
        "widget": p.widget.value if p.widget else None,
        "placeholder": p.placeholder,
        "visible_if": p.visible_if,
    }


# --- Factories ---------------------------------------------------------------
def _spec(
    type_id: str,
    handler: Handler,
    description: str,
    *,
    ui: dict[str, Any] | None = None,
    input_ports: tuple[PortSpec, ...] = (),
    output_ports: tuple[PortSpec, ...] = (),
    params: tuple[ParamSpec, ...] = (),
    semantics_requires: tuple[str, ...] = (),
) -> NodeSpec:
    return NodeSpec(
        type_id=type_id,
        description=description,
        handler=handler,
        ui=ui or {},
        input_ports=input_ports,
        output_ports=output_ports,
        params=params,
        semantics_requires=semantics_requires,
    )


def _spec_from_yaml(yaml_path: Path, handler: Handler) -> NodeSpec:
    """Load NodeSpec metadata from a sibling YAML file."""
    raw = yaml.safe_load(yaml_path.read_text())

    def _ports(seq: list[dict] | None) -> tuple[PortSpec, ...]:
        return tuple(
            PortSpec(
                name=p["name"],
                type=PortType(p.get("type", "any")),
                description=p.get("description", ""),
                optional=bool(p.get("optional", False)),
                store_at=p.get("store_at", ""),
            )
            for p in (seq or [])
        )

    def _params(seq: list[dict] | None) -> tuple[ParamSpec, ...]:
        out = []
        for p in seq or []:
            try:
                ptype = ParamType(p.get("type", "string"))
            except ValueError:
                ptype = ParamType.STRING
            widget = None
            if p.get("widget"):
                try:
                    widget = Widget(p["widget"])
                except ValueError:
                    widget = None
            out.append(
                ParamSpec(
                    name=p["name"],
                    type=ptype,
                    description=p.get("description", ""),
                    required=bool(p.get("required", False)),
                    default=p.get("default"),
                    enum=tuple(p.get("enum") or ()),
                    widget=widget,
                    placeholder=p.get("placeholder", ""),
                    visible_if=p.get("visible_if"),
                )
            )
        return tuple(out)

    return NodeSpec(
        type_id=raw["type_id"],
        description=raw.get("description", ""),
        handler=handler,
        ui=raw.get("ui") or {},
        input_ports=_ports(raw.get("input_ports")),
        output_ports=_ports(raw.get("output_ports")),
        params=_params(raw.get("params")),
        semantics_requires=tuple(raw.get("semantics", {}).get("requires") or ()),
    )
  