"""Pydantic models for task-enforcer v2.1 schema.

Matches the structure of tasks.json exactly, handling both simple (int) and
structured (dict) priority formats found in real data.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

KanbanStatus = Literal["ready", "backlog", "blocked", "in_progress", "done", "archived"]
EisenhowerQuadrant = Literal[
    "urgent-important",
    "important-not-urgent",
    "urgent-not-important",
    "not-urgent-not-important",
]
GatingStrategy = Literal[
    "auto",
    "human-claim",
    "dependency",
    "none",
    "hitl-approval",
    "ppac-critic",
]


class GoNoGo(BaseModel):
    """Go/NoGo gating decision metadata."""

    type: str = "auto"
    gating: str = "none"


class Decisions(BaseModel):
    """PPAC decision tracking for a task."""

    gonogo: GoNoGo = Field(default_factory=GoNoGo)
    ppac_critic: bool = False
    human_claim: bool = False
    hitl_required: bool = False


class Priority(BaseModel):
    """Eisenhower + RPE priority model.

    Accepts both legacy int format (1-4) and structured dict format.
    """

    level: int = Field(default=3, ge=1, le=4)
    eisenhower: EisenhowerQuadrant = "important-not-urgent"
    rpe_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    value_score: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, data: Any) -> Any:
        """Accept Priority from a plain int (legacy format) or dict."""
        if isinstance(data, int):
            return {"level": data}
        return data


class RepositoryTask(BaseModel):
    """A single task entry from tasks.json."""

    id: str
    priority: Priority = Field(default_factory=Priority)
    decisions: Decisions = Field(default_factory=Decisions)
    kanban_status: KanbanStatus = "backlog"
    subject: str
    description: str = ""
    files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    done: bool = False
    definition_of_done: list[str] | None = None
    rpe_hook: str | None = None
    references: list[str] | None = None
    cross_references: list[str] | None = None


class MetaConfig(BaseModel):
    """Metadata section of tasks.json."""

    repository: str
    package: str = ""
    role: str = ""
    last_updated: date | str = ""
    schema_version: str = "2.1"
    schema_name: str = Field(default="task-enforcer-v2", alias="schema")
    description: str = ""
    framework_reference: str = ""


class TaskRegistry(BaseModel):
    """Full tasks.json document."""

    meta: MetaConfig
    completed: list[str] = Field(default_factory=list)
    pending: list[RepositoryTask] = Field(default_factory=list)
    last_updated: date | str = ""
