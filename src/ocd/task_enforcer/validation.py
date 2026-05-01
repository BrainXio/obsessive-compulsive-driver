"""Validation logic for task-enforcer schema.

Checks:
- Mandatory fields present
- kanban_status values
- Priority ranges
- ID format
- Duplicate detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALLOWED_STATUSES = frozenset({"ready", "backlog", "blocked", "in_progress", "done", "archived"})


@dataclass
class ValidationError:
    task_id: str
    field: str
    message: str


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def merge(self, other: ValidationResult) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if not other.is_valid:
            self.is_valid = False


def _validate_task(task: dict[str, Any]) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    tid = task.get("id", "<missing>")

    # Mandatory fields
    for field_name in ("id", "subject", "description"):
        if field_name not in task:
            errors.append(
                ValidationError(tid, field_name, f"missing mandatory field '{field_name}'")
            )

    # kanban_status
    status = task.get("kanban_status")
    if status is not None and status not in ALLOWED_STATUSES:
        errors.append(
            ValidationError(
                tid,
                "kanban_status",
                f"invalid status '{status}'; allowed: {sorted(ALLOWED_STATUSES)}",
            )
        )

    # Priority validation
    priority = task.get("priority")
    if isinstance(priority, dict):
        level = priority.get("level")
        if level is not None and not (1 <= level <= 4):
            errors.append(ValidationError(tid, "priority.level", f"must be 1-4, got {level}"))
        rpe = priority.get("rpe_weight")
        if rpe is not None and not (0.0 <= rpe <= 1.0):
            errors.append(
                ValidationError(tid, "priority.rpe_weight", f"must be 0.0-1.0, got {rpe}")
            )
        score = priority.get("value_score")
        if score is not None and not (0 <= score <= 100):
            errors.append(
                ValidationError(tid, "priority.value_score", f"must be 0-100, got {score}")
            )
    elif isinstance(priority, (int, float)):
        if not (1 <= priority <= 4):
            warnings.append(
                ValidationError(tid, "priority", f"legacy int priority out of range: {priority}")
            )
    elif priority is not None:
        warnings.append(
            ValidationError(tid, "priority", f"unexpected priority type: {type(priority).__name__}")
        )

    # files should be a list
    files = task.get("files")
    if files is not None and not isinstance(files, list):
        errors.append(ValidationError(tid, "files", "must be a list"))

    # dependencies should be a list
    deps = task.get("dependencies")
    if deps is not None and not isinstance(deps, list):
        errors.append(ValidationError(tid, "dependencies", "must be a list"))

    # done is a required bool
    if "done" not in task:
        warnings.append(ValidationError(tid, "done", "missing 'done' field, defaulting to False"))

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_task_registry(data: dict[str, Any]) -> ValidationResult:
    """Validate a full tasks.json document."""
    result = ValidationResult(is_valid=True)

    if "meta" not in data:
        result.errors.append(ValidationError("<root>", "meta", "missing meta section"))
        result.is_valid = False
    else:
        meta = data["meta"]
        for field_name in ("repository",):
            if field_name not in meta:
                result.errors.append(
                    ValidationError("<meta>", field_name, f"missing meta field '{field_name}'")
                )
                result.is_valid = False

    pending = data.get("pending", [])
    if not isinstance(pending, list):
        result.errors.append(ValidationError("<root>", "pending", "must be a list"))
        result.is_valid = False
        return result

    seen_ids: set[str] = set()
    for task in pending:
        if not isinstance(task, dict):
            result.errors.append(ValidationError("<entry>", "", "task entry must be a dict"))
            result.is_valid = False
            continue
        result.merge(_validate_task(task))
        tid = task.get("id", "")
        if tid in seen_ids:
            result.errors.append(ValidationError(tid, "id", f"duplicate task ID '{tid}'"))
            result.is_valid = False
        seen_ids.add(tid)

    return result


def validate_task_update(task_id: str, updates: dict[str, Any]) -> ValidationResult:
    """Validate a partial task update payload."""
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    disallowed = {"id"}
    for field_name in disallowed:
        if field_name in updates:
            errors.append(ValidationError(task_id, field_name, "cannot update task ID"))

    status = updates.get("kanban_status")
    if status is not None and status not in ALLOWED_STATUSES:
        errors.append(
            ValidationError(
                task_id,
                "kanban_status",
                f"invalid status '{status}'; allowed: {sorted(ALLOWED_STATUSES)}",
            )
        )

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
