"""Tests for cross-repo task dependency resolution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from ocd.task_enforcer.cross_repo import (
    REPO_NAMES,
    get_task_repo,
    load_all_registries,
    resolve_task,
    validate_all_cross_references,
    validate_dependencies,
)


def _write_tasks_json(path: Path, pending: list[dict], **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"pending": pending, **extra}
    path.write_text(json.dumps(data))


class TestResolveTask:
    def test_resolve_finds_task_in_registry(self) -> None:
        registries = {
            "test-repo": {
                "pending": [
                    {"id": "task-1", "subject": "hello"},
                    {"id": "task-2", "subject": "world"},
                ],
            },
        }
        result = resolve_task("task-1", registries)
        assert result is not None
        assert result["id"] == "task-1"
        assert result["_repo"] == "test-repo"

    def test_resolve_returns_none_for_missing(self) -> None:
        registries = {"test-repo": {"pending": []}}
        assert resolve_task("nonexistent", registries) is None

    def test_resolve_finds_task_across_multiple_repos(self) -> None:
        registries = {
            "repo-a": {"pending": [{"id": "a-1", "subject": "first"}]},
            "repo-b": {"pending": [{"id": "b-1", "subject": "second"}]},
        }
        result = resolve_task("b-1", registries)
        assert result is not None
        assert result["_repo"] == "repo-b"


class TestGetTaskRepo:
    def test_returns_repo_name(self) -> None:
        registries = {"my-repo": {"pending": [{"id": "x", "subject": "y"}]}}
        assert get_task_repo("x", registries) == "my-repo"

    def test_returns_none_for_missing(self) -> None:
        assert get_task_repo("nope", {}) is None


class TestValidateDependencies:
    def test_all_deps_resolve(self) -> None:
        registries = {
            "repo-a": {
                "pending": [
                    {"id": "a-1", "subject": "parent", "dependencies": ["b-1"]},
                ],
            },
            "repo-b": {
                "pending": [
                    {"id": "b-1", "subject": "child"},
                ],
            },
        }
        result = validate_dependencies("a-1", ["b-1"], registries)
        assert result.is_valid is True
        assert "b-1" in result.resolved

    def test_unresolvable_dep(self) -> None:
        registries = {"repo-a": {"pending": []}}
        result = validate_dependencies("a-1", ["ghost-task"], registries)
        assert result.is_valid is False
        assert len(result.unresolvable) == 1
        assert "not found" in result.unresolvable[0].message

    def test_circular_dependency(self) -> None:
        registries = {
            "repo-a": {
                "pending": [
                    {"id": "a-1", "subject": "parent", "dependencies": ["b-1"]},
                ],
            },
            "repo-b": {
                "pending": [
                    {"id": "b-1", "subject": "child", "dependencies": ["a-1"]},
                ],
            },
        }
        result = validate_dependencies("a-1", ["b-1"], registries)
        assert result.is_valid is False
        assert len(result.circular) >= 1

    def test_done_dependency_does_not_block(self) -> None:
        registries = {
            "repo-a": {
                "pending": [
                    {"id": "a-1", "subject": "parent", "dependencies": ["b-1"]},
                ],
            },
            "repo-b": {
                "pending": [
                    {"id": "b-1", "subject": "child", "done": True},
                ],
            },
        }
        result = validate_dependencies("a-1", ["b-1"], registries)
        assert result.is_valid is True


class TestValidateAllCrossReferences:
    def test_valid_xrefs(self) -> None:
        registries = {
            "repo-a": {
                "pending": [
                    {"id": "a-1", "subject": "one", "cross_references": ["b-1"]},
                ],
            },
            "repo-b": {
                "pending": [
                    {"id": "b-1", "subject": "two"},
                ],
            },
        }
        result = validate_all_cross_references(registries)
        assert result.is_valid is True

    def test_broken_xref(self) -> None:
        registries = {
            "repo-a": {
                "pending": [
                    {"id": "a-1", "subject": "one", "cross_references": ["ghost"]},
                ],
            },
        }
        result = validate_all_cross_references(registries)
        assert result.is_valid is False
        assert len(result.unresolvable) == 1


class TestLoadAllRegistries:
    def test_loads_existing_repos(self, tmp_path: Path) -> None:
        for repo_name in REPO_NAMES:
            _write_tasks_json(
                tmp_path / repo_name / "tasks.json",
                [{"id": f"{repo_name}-1", "subject": "task"}],
                meta={"repository": repo_name},
            )

        with mock.patch(
            "ocd.task_enforcer.cross_repo._find_repos_root",
            return_value=tmp_path,
        ):
            registries = load_all_registries(tmp_path / "obsessive-compulsive-driver")

        assert len(registries) == 4
        for repo_name in REPO_NAMES:
            assert repo_name in registries

    def test_omits_missing_repos(self, tmp_path: Path) -> None:
        _write_tasks_json(
            tmp_path / "obsessive-compulsive-driver" / "tasks.json",
            [{"id": "ocd-1", "subject": "only"}],
        )

        with mock.patch(
            "ocd.task_enforcer.cross_repo._find_repos_root",
            return_value=tmp_path,
        ):
            registries = load_all_registries(tmp_path / "obsessive-compulsive-driver")

        assert "obsessive-compulsive-driver" in registries
        assert len(registries) == 1
