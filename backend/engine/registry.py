"""
Auto-discovers every `NODE_SPEC` declared under `engine/nodes/`.

Adding a node = drop a new `<name>.py` (and usually `<name>.yaml`)
into `engine/nodes/`. No central list to edit.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Iterable

from . import nodes as _nodes_pkg
from .node_spec import Handler, NodeSpec

logger = logging.getLogger(__name__)


def _discover() -> tuple[NodeSpec, ...]:
    found: dict[str, NodeSpec] = {}
    for info in pkgutil.iter_modules(_nodes_pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{_nodes_pkg.__name__}.{info.name}")
        specs: list[NodeSpec] = []
        if isinstance(getattr(module, "NODE_SPEC", None), NodeSpec):
            specs.append(module.NODE_SPEC)
        grouped = getattr(module, "NODE_SPECS", ())
        if isinstance(grouped, (list, tuple)):
            specs.extend(s for s in grouped if isinstance(s, NodeSpec))
        for s in specs:
            if s.type_id in found:
                raise RuntimeError(
                    f"Duplicate NODE_SPEC type_id '{s.type_id}' "
                    f"defined in engine/nodes/{info.name}.py and elsewhere."
                )
            found[s.type_id] = s
    logger.info("Loaded %d node specs from engine/nodes/", len(found))
    return tuple(sorted(found.values(), key=lambda s: s.type_id))


_SPECS: tuple[NodeSpec, ...] = _discover()
NODE_SPECS: dict[str, NodeSpec] = {s.type_id: s for s in _SPECS}
NODE_HANDLERS: dict[str, Handler] = {s.type_id: s.handler for s in _SPECS}


def all_specs() -> Iterable[NodeSpec]:
    return _SPECS


def get_spec(type_id: str) -> NodeSpec:
    if type_id not in NODE_SPECS:
        raise ValueError(f"Unknown node type '{type_id}'")
    return NODE_SPECS[type_id]


def contracts_document(version: str = "1.0") -> dict:
    return {
        "version": version,
        "nodes": [s.contract for s in _SPECS],
    }


  

def block_registry() -> list[dict]:
    """Frontend-friendly compact list (matches the TS blockRegistry() shape).

    Includes per-node `fields` so the UI can render a config form without
    hardcoding any node knowledge.
    """
    from dataclasses import asdict, is_dataclass
    out = []
    for s in _SPECS:
        ui = s.ui or {}
        params: list[dict] = []
        for p in s.params:
            if is_dataclass(p):
                d = asdict(p)
                if "widget" in d and d["widget"] is not None and hasattr(d["widget"], "value"):
                    d["widget"] = d["widget"].value
                if "type" in d and hasattr(d["type"], "value"):
                    d["type"] = d["type"].value
                params.append(d)
            elif isinstance(p, dict):
                params.append(dict(p))
        out.append({
            "type": s.type_id,
            "label": ui.get("display_name") or s.type_id.replace("_", " ").title(),
            "description": s.description,
            "category": (ui.get("palette") or {}).get("section", {}).get("id", "other"),
            "icon": ui.get("icon", "Box"),
            "color": ui.get("color", "#7c3aed"),
            "fields": params,
        })
    return out
