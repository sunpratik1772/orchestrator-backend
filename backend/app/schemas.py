"""Pydantic request/response shapes mirroring the existing TS frontend's contract."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class NodeIn(BaseModel):
    id: str
    type: str
    label: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    data: Optional[dict[str, Any]] = None
    position: Optional[dict[str, float]] = None


class EdgeIn(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = ""
    nodes: list[NodeIn] = Field(default_factory=list)
    edges: list[EdgeIn] = Field(default_factory=list)
    status: Optional[Literal["draft", "active", "archived"]] = "draft"


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[list[NodeIn]] = None
    edges: Optional[list[EdgeIn]] = None
    status: Optional[Literal["draft", "active", "archived"]] = None


class RunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    trigger: str = "manual"


class CopilotMessage(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
  