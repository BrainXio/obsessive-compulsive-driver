"""Tests for task-enforcer schema models and validation."""

from __future__ import annotations

import pytest

from ocd.task_enforcer.models import (
    MetaConfig,
    Priority,
    RepositoryTask,
    TaskRegistry,
)
from ocd.task_enforcer.validation import (
    ValidationError,
    ValidationResult,
    validate_task_registry,
    validate_task_update,
)


class TestPriorityModel:
    """Priority parsing including legacy int coercion."""

    def test_default_priority(self) -> None:
        p = Priority()
        assert p.level == 3
        assert p.eisenhower == "important-not-urgent"
        assert p.rpe_weight == 0.5
        assert p.value_score == 50

    def test_legacy_int_coercion(self) -> None:
        p = Priority.model_validate(2)
        assert p.level == 2

    def test_dict_parsing(self) -> None:
        p = Priority.model_validate(
            {"level": 1, "eisenhower": "urgent-important", "rpe_weight": 0.9, "value_score": 88}
        )
        assert p.level == 1
        assert p.rpe_weight == 0.9

    def test_level_bounds(self) -> None:
        with pytest.raises(ValueError):
            Priority(level=0)
        with pytest.raises(ValueError):
            Priority(level=5)

    def test_rpe_weight_bounds(self) -> None:
        with pytest.raises(ValueError):
            Priority(rpe_weight=-0.1)
        with pytest.raises(ValueError):
            Priority(rpe_weight=1.1)


class TestRepositoryTaskModel:
    """RepositoryTask creation and defaults."""

    def test_minimal_task(self) -> None:
        task = RepositoryTask(id="ocd-1", subject="test task")
        assert task.id == "ocd-1"
        assert task.subject == "test task"
        assert task.kanban_status == "backlog"
        assert task.done is False
        assert task.priority.level == 3

    def test_full_task(self) -> None:
        task = RepositoryTask(
            id="ocd-2",
            priority=2,
            decisions={"gonogo": {"type": "auto", "gating": "none"}},
            kanban_status="ready",
            subject="full task",
            description="desc",
            files=["a.py"],
            acceptance=["pass"],
            dependencies=["ocd-1"],
            blocks=["ocd-3"],
            done=False,
        )
        assert task.priority.level == 2
        assert task.decisions.gonogo.type == "auto"

    def test_invalid_kanban_status(self) -> None:
        with pytest.raises(ValueError):
            RepositoryTask(id="x", subject="y", kanban_status="unknown")


class TestTaskRegistryModel:
    """TaskRegistry parsing from dict."""

    def test_empty_registry(self) -> None:
        registry = TaskRegistry(meta=MetaConfig(repository="test"))
        assert registry.meta.repository == "test"
        assert registry.pending == []

    def test_registry_with_tasks(self) -> None:
        registry = TaskRegistry(
            meta=MetaConfig(repository="ocd"),
            pending=[
                RepositoryTask(id="ocd-1", subject="first"),
                RepositoryTask(id="ocd-2", subject="second"),
            ],
        )
        assert len(registry.pending) == 2


class TestTaskValidation:
    """Validation logic for task entries."""

    def test_valid_task(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "kanban_status": "ready",
            "priority": {"level": 1, "rpe_weight": 0.9, "value_score": 88},
            "files": ["a.py"],
            "dependencies": [],
            "done": False,
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert result.is_valid
        assert result.errors == []

    def test_missing_mandatory_fields(self) -> None:
        task = {"id": "ocd-1"}  # missing subject and description
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert not result.is_valid
        fields = [e.field for e in result.errors]
        assert "subject" in fields
        assert "description" in fields

    def test_invalid_kanban_status(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "kanban_status": "invalid",
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert not result.is_valid
        assert any(e.field == "kanban_status" for e in result.errors)

    def test_duplicate_task_id(self) -> None:
        tasks = [
            {"id": "ocd-1", "subject": "first", "description": "d"},
            {"id": "ocd-1", "subject": "second", "description": "d"},
        ]
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": tasks,
            }
        )
        assert not result.is_valid
        assert any("duplicate" in e.message for e in result.errors)

    def test_invalid_priority_level(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "priority": {"level": 5},
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert not result.is_valid
        assert any(e.field == "priority.level" for e in result.errors)

    def test_legacy_int_priority_warning(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "priority": 5,
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        # Legacy priority should generate warning, not error
        assert any("legacy" in w.message for w in result.warnings)

    def test_missing_meta(self) -> None:
        result = validate_task_registry({"pending": []})
        assert not result.is_valid
        assert any(e.field == "meta" for e in result.errors)

    def test_missing_repository_in_meta(self) -> None:
        result = validate_task_registry(
            {
                "meta": {},
                "pending": [],
            }
        )
        assert not result.is_valid
        assert any(e.field == "repository" for e in result.errors)

    def test_files_must_be_list(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "files": "not a list",
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert not result.is_valid
        assert any(e.field == "files" for e in result.errors)

    def test_dependencies_must_be_list(self) -> None:
        task = {
            "id": "ocd-1",
            "subject": "test",
            "description": "desc",
            "dependencies": "ocd-2",
        }
        result = validate_task_registry(
            {
                "meta": {"repository": "ocd"},
                "pending": [task],
            }
        )
        assert not result.is_valid
        assert any(e.field == "dependencies" for e in result.errors)


class TestTaskUpdateValidation:
    """Partial update validation."""

    def test_valid_status_update(self) -> None:
        result = validate_task_update("ocd-1", {"kanban_status": "in_progress"})
        assert result.is_valid

    def test_disallowed_id_update(self) -> None:
        result = validate_task_update("ocd-1", {"id": "ocd-2"})
        assert not result.is_valid
        assert any(e.field == "id" for e in result.errors)

    def test_invalid_status_update(self) -> None:
        result = validate_task_update("ocd-1", {"kanban_status": "bad"})
        assert not result.is_valid
        assert any(e.field == "kanban_status" for e in result.errors)


class TestValidationResultMerge:
    """Result composition."""

    def test_merge_combines_errors(self) -> None:
        r1 = ValidationResult(is_valid=True)
        r2 = ValidationResult(is_valid=False, errors=[ValidationError("a", "f", "m")])
        r1.merge(r2)
        assert not r1.is_valid
        assert len(r1.errors) == 1
