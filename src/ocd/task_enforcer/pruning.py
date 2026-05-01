"""Stale task detection and pruning.

Identifies low-value, stale tasks for archival review based on
Eisenhower priority and RPE-weighted scoring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STALE_DAYS_THRESHOLD = 30
PRIORITY_STALE_THRESHOLD = 3
VALUE_SCORE_STALE_THRESHOLD = 50


@dataclass
class StaleTask:
    """A task flagged as stale."""

    task_id: str
    subject: str
    kanban_status: str
    priority_level: int
    value_score: float
    rpe_weight: float
    age_days: float
    decayed_score: float | None = None


@dataclass
class PruningReport:
    """Result of a pruning analysis."""

    analyzed: int
    stale: list[StaleTask] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def _compute_age_days(task: dict[str, Any]) -> float | None:
    """Compute age in days from last_updated or kanban_status timestamp."""
    updated = task.get("last_updated")
    if updated is None:
        return None
    try:
        if isinstance(updated, str):
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        else:
            dt = updated
    except (ValueError, TypeError):
        return None
    return (datetime.now(UTC) - dt).total_seconds() / 86400


def _decay_score(original_score: float, age_days: float) -> float:
    """Apply exponential decay to a task's value score based on age.

    Decay constant chosen so that a score decays to ~50% after 60 days.
    """
    k = 0.0116  # ln(2) / 60
    return original_score * (1.0 / (1.0 + k * age_days))


def find_stale_tasks(tasks_json_path: Path, dry_run: bool = True) -> PruningReport:
    """Identify stale tasks in a tasks.json file.

    A task is stale when:
    - kanban_status is 'backlog'
    - priority level >= STALE_DAYS_THRESHOLD (P3+)
    - value_score < VALUE_SCORE_STALE_THRESHOLD
    - Age > STALE_DAYS_THRESHOLD

    Args:
        tasks_json_path: Path to the tasks.json file.
        dry_run: If True, only reports tasks without modifying the file.

    Returns:
        A PruningReport with the list of stale tasks and suggestions.
    """
    data = json.loads(tasks_json_path.read_text())
    pending = data.get("pending", [])
    report = PruningReport(analyzed=len(pending))

    for task in pending:
        if not isinstance(task, dict):
            continue

        tid = task.get("id", "?")
        status = task.get("kanban_status", "backlog")

        if status != "backlog":
            continue

        priority = task.get("priority", {})
        if isinstance(priority, dict):
            level = priority.get("level", 99)
            value = priority.get("value_score", 0)
            rpe = priority.get("rpe_weight", 0)
        elif isinstance(priority, (int, float)):
            level = priority
            value = 0
            rpe = 0
        else:
            level = 99
            value = 0
            rpe = 0

        # Only flag P3+ and low-value tasks
        if level < PRIORITY_STALE_THRESHOLD or value >= VALUE_SCORE_STALE_THRESHOLD:
            continue

        age_days = _compute_age_days(task)
        if age_days is None or age_days < STALE_DAYS_THRESHOLD:
            continue

        decayed = _decay_score(value, age_days)
        stale = StaleTask(
            task_id=tid,
            subject=task.get("subject", ""),
            kanban_status=status,
            priority_level=level,
            value_score=value,
            rpe_weight=rpe,
            age_days=round(age_days, 1),
            decayed_score=round(decayed, 1),
        )
        report.stale.append(stale)

    # Build suggestions
    if report.stale:
        report.suggestions.append(
            f"{len(report.stale)} stale task(s) found. Review and archive via "
            f'ocd_task_update(id, {{"kanban_status": "archived"}}).'
        )
        report.suggestions.append(
            "Human review required before archival. Use ocd_task_get(id) for details."
        )
    else:
        report.suggestions.append("No stale tasks found.")

    return report


def archived_stale_tasks(tasks_json_path: Path) -> PruningReport:
    """Identify and archive stale tasks (non-dry-run).

    Modifies the tasks.json file on disk. Use with caution.
    """
    report = find_stale_tasks(tasks_json_path, dry_run=True)

    if not report.stale:
        return report

    data = json.loads(tasks_json_path.read_text())
    stale_ids = {s.task_id for s in report.stale}
    for task in data.get("pending", []):
        if isinstance(task, dict) and task.get("id") in stale_ids:
            task["kanban_status"] = "archived"
            task["_archived_reason"] = "pruning: stale task"
            task["_archived_date"] = datetime.now(UTC).isoformat()

    tasks_json_path.write_text(json.dumps(data, indent=2) + "\n")
    return report
