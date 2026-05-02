"""Cross-repo task dependency resolution and validation.

Resolves task IDs across all four BrainXio repos, validates that
cross-repo dependency references are resolvable, and detects circular
dependencies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_NAMES = (
    "another-intelligence",
    "attention-deficit-hyperactivity-driver",
    "autism-spectrum-driver",
    "obsessive-compulsive-driver",
)

_REPO_TO_CENTRALIZED: dict[str, str] = {
    "another-intelligence": "ai",
    "attention-deficit-hyperactivity-driver": "adhd",
    "autism-spectrum-driver": "asd",
    "obsessive-compulsive-driver": "ocd",
}


@dataclass
class DependencyIssue:
    """A single cross-repo dependency problem."""

    task_id: str
    dependency_id: str
    repo: str
    message: str


@dataclass
class CrossRepoResult:
    """Result of cross-repo dependency validation."""

    is_valid: bool
    resolved: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolvable: list[DependencyIssue] = field(default_factory=list)
    circular: list[list[str]] = field(default_factory=list)


def _find_repos_root(project_root: Path) -> Path:
    """Walk up from *project_root* to find the parent containing all repos."""
    for parent in [project_root, *project_root.parents]:
        siblings = [parent / r for r in REPO_NAMES]
        if sum(1 for s in siblings if (s / "tasks.json").exists()) >= 2:
            return parent
    return project_root.parent


def _resolve_tasks_path(repo_name: str) -> Path | None:
    """Return the effective tasks.json path for *repo_name*.

    BrainXio repos use centralized task files under ~/.brainxio/ocd/tasks/.
    Falls back to repo-local tasks.json when no centralized mapping exists.
    """
    short = _REPO_TO_CENTRALIZED.get(repo_name)
    if short:
        centralized = Path.home() / ".brainxio" / "ocd" / "tasks" / f"{short}.json"
        if centralized.exists():
            return centralized
    return None


def load_all_registries(project_root: Path) -> dict[str, dict[str, Any]]:
    """Load tasks.json from all available BrainXio repos.

    Returns:
        Mapping of repo name → tasks.json data. Missing repos are omitted.
    """
    repos_root = _find_repos_root(project_root)
    registries: dict[str, dict[str, Any]] = {}
    for repo_name in REPO_NAMES:
        # Prefer centralized task file
        cpath = _resolve_tasks_path(repo_name)
        if cpath and cpath.exists():
            registries[repo_name] = json.loads(cpath.read_text())
            continue
        # Fallback to repo-local tasks.json
        path = repos_root / repo_name / "tasks.json"
        if path.exists():
            registries[repo_name] = json.loads(path.read_text())
    return registries


def resolve_task(task_id: str, registries: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Find a task by ID across all loaded registries.

    Returns the first matching task dict with ``_repo`` added, or None.
    """
    for repo_name, data in registries.items():
        for task in data.get("pending", []):
            if isinstance(task, dict) and task.get("id") == task_id:
                result = dict(task)
                result["_repo"] = repo_name
                return result
    return None


def get_task_repo(task_id: str, registries: dict[str, dict[str, Any]]) -> str | None:
    """Return the repo name that contains *task_id*, or None."""
    for repo_name, data in registries.items():
        for task in data.get("pending", []):
            if isinstance(task, dict) and task.get("id") == task_id:
                return repo_name
    return None


def validate_dependencies(
    task_id: str,
    dependencies: list[str],
    registries: dict[str, dict[str, Any]],
    visited: frozenset[str] | None = None,
) -> CrossRepoResult:
    """Validate that all *dependencies* resolve and have no cycles.

    Args:
        task_id: The task whose dependencies are being checked.
        dependencies: List of task IDs this task depends on.
        registries: All loaded task registries.
        visited: Set of already-visited task IDs for cycle detection.
    """
    result = CrossRepoResult(is_valid=True)
    visited = (visited or frozenset()) | {task_id}

    for dep_id in dependencies:
        # Resolve the dependency
        dep_task = resolve_task(dep_id, registries)
        if dep_task is None:
            result.unresolvable.append(
                DependencyIssue(
                    task_id=task_id,
                    dependency_id=dep_id,
                    repo="unknown",
                    message=f"dependency '{dep_id}' not found in any repo",
                )
            )
            result.is_valid = False
            continue

        result.resolved[dep_id] = dep_task

        # Cycle detection
        if dep_id in visited:
            result.circular.append(list(visited) + [dep_id])
            result.unresolvable.append(
                DependencyIssue(
                    task_id=task_id,
                    dependency_id=dep_id,
                    repo=dep_task.get("_repo", "unknown"),
                    message=f"circular dependency: {task_id} → {dep_id}",
                )
            )
            result.is_valid = False
            continue

        # Check if dependency is marked done (shouldn't block)
        if dep_task.get("done"):
            continue

        # Recurse into dependency's own deps
        sub_deps = dep_task.get("dependencies", [])
        if sub_deps:
            sub_result = validate_dependencies(dep_id, sub_deps, registries, visited)
            result.resolved.update(sub_result.resolved)
            result.unresolvable.extend(sub_result.unresolvable)
            result.circular.extend(sub_result.circular)
            if not sub_result.is_valid:
                result.is_valid = False

    return result


def validate_all_cross_references(
    registries: dict[str, dict[str, Any]],
) -> CrossRepoResult:
    """Validate cross-references across all loaded registries.

    Checks every task's ``cross_references`` field for resolvability.
    """
    result = CrossRepoResult(is_valid=True)

    for repo_name, data in registries.items():
        for task in data.get("pending", []):
            if not isinstance(task, dict):
                continue
            tid = task.get("id", "?")
            xrefs = task.get("cross_references", [])
            for xref_id in xrefs:
                if resolve_task(xref_id, registries) is None:
                    result.unresolvable.append(
                        DependencyIssue(
                            task_id=tid,
                            dependency_id=xref_id,
                            repo=repo_name,
                            message=f"cross-reference '{xref_id}' not found in any repo",
                        )
                    )
                    result.is_valid = False

            # Also validate hard dependencies
            deps = task.get("dependencies", [])
            if deps:
                sub = validate_dependencies(tid, deps, registries)
                result.resolved.update(sub.resolved)
                result.unresolvable.extend(sub.unresolvable)
                result.circular.extend(sub.circular)
                if not sub.is_valid:
                    result.is_valid = False

    return result
