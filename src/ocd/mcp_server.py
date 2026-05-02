"""FastMCP server for OCD — discipline & enforcement layer, no CLI, no scripts."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

from ocd.modes import ALLOWED_MODES
from ocd.precedents import check_precedents, list_precedents, remember_issue
from ocd.rules import (
    get_rules as get_ocd_rules,
)
from ocd.standards_data import (
    check_message,
    compute_standards_hash,
    get_standards_reference,
    verify_standards_hash,
)
from ocd.task_enforcer.validation import validate_task_update
from ocd.tools.standards_checker import _CHECKER_NAMES, StandardsChecker

logging.basicConfig(level=logging.INFO, stream=sys.stderr)

mcp = FastMCP(
    "ocd",
    instructions=(
        "OCD discipline & enforcement layer. Use these tools to check quality gates, "
        "verify standards, scan for secrets, run formatters, and lint code."
    ),
)

# ── Mode state ────────────────────────────────────────────────────────────────

_current_mode: str = "developer"


def _find_project_root() -> Path:
    """Find project root by walking up from CWD looking for .git/."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return parent
    return cwd


_REPO_TO_CENTRALIZED: dict[str, str] = {
    "another-intelligence": "ai",
    "attention-deficit-hyperactivity-driver": "adhd",
    "autism-spectrum-driver": "asd",
    "obsessive-compulsive-driver": "ocd",
}


def _resolve_tasks_path(root: Path) -> Path:
    """Return the effective tasks.json path for *root*.

    BrainXio repos use centralized task files under ~/.brainxio/ocd/tasks/.
    Falls back to repo-local tasks.json when no centralized mapping exists.
    """
    short = _REPO_TO_CENTRALIZED.get(root.name)
    if short:
        centralized = Path.home() / ".brainxio" / "ocd" / "tasks" / f"{short}.json"
        if centralized.exists():
            return centralized
    return root / "tasks.json"


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _tool_available(binary: str) -> bool:
    """Check if a binary is available on PATH."""
    return shutil.which(binary) is not None


def _run_tool(cmd: list[str], timeout: int = 60, cwd: Path | None = None) -> tuple[bool, str]:
    """Run a subprocess tool, return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or _find_project_root()),
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except FileNotFoundError:
        return True, "skipped (not installed)"

    output = (result.stderr + result.stdout).strip()
    return result.returncode == 0, output


# ── Mode tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_set_mode(mode: str) -> str:
    """Switch the active rule/gate/skill set.

    Args:
        mode: The mode to activate. Available: developer, research, review, ops, personal.
    """
    if mode not in ALLOWED_MODES:
        allowed = ", ".join(sorted(ALLOWED_MODES))
        return json.dumps({"ok": False, "error": f"Unknown mode '{mode}'. Allowed: {allowed}"})
    global _current_mode
    _current_mode = mode
    return json.dumps({"ok": True, "mode": mode})


@mcp.tool()
async def ocd_get_mode() -> str:
    """Return the currently active mode."""
    return json.dumps({"mode": _current_mode})


# ── Precedent tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_remember_issue(
    description: str, check: str, fix: str, scope: str = "both", severity: str = "warning"
) -> str:
    """Record a new issue pattern so it can be prevented in future.

    Args:
        description: Short human-readable description of the issue.
        check: Shell command that returns 0 if the issue is present.
        fix: Human-readable instructions to resolve the issue.
        scope: When to check this — "local", "ci", or "both" (default).
        severity: Base severity — "info", "warning", "error", or "fatal".
    """
    result = remember_issue(
        description=description,
        check=check,
        fix=fix,
        scope=scope,
        severity=severity,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
async def ocd_check_precedents(scope: str = "both") -> str:
    """Run all recorded precedent checks for the given scope.

    If a precedent has been hit 2+ times, its effective severity escalates
    by one level (warning -> error, error -> fatal).

    Args:
        scope: "local", "ci", or "both" (default).
    """
    result = check_precedents(scope=scope)
    return json.dumps(result, indent=2)


@mcp.tool()
async def ocd_list_precedents(scope: str | None = None, min_hits: int = 0) -> str:
    """List recorded issue precedents.

    Args:
        scope: Filter by scope — "local", "ci", or omit for all.
        min_hits: Only show precedents with at least this many hits.
    """
    result = list_precedents(scope=scope, min_hits=min_hits)
    return json.dumps(result, indent=2)


# ── Quality gate tools ───────────────────────────────────────────────────────


@mcp.tool()
async def ocd_check() -> str:
    """Run fast local quality gate.

    Checks: branch protection, standards hash, staged secret scan, ruff check.
    Target: < 10 seconds for typical use.
    """
    root = _find_project_root()
    results: list[dict[str, Any]] = []

    # Branch protection
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        branch = r.stdout.strip()
        if branch == "main":
            results.append(
                {
                    "check": "branch-protection",
                    "status": "fail",
                    "detail": "commits on main are prohibited",
                }
            )
        else:
            results.append(
                {"check": "branch-protection", "status": "pass", "detail": f"branch: {branch}"}
            )
    except Exception:
        results.append(
            {
                "check": "branch-protection",
                "status": "pass",
                "detail": "not a git repo, skipped",
            }
        )

    # Standards verify
    std_result = verify_standards_hash()
    if std_result["match"]:
        results.append(
            {
                "check": "standards-verify",
                "status": "pass",
                "detail": f"v{std_result['version']} [{std_result['computed_hash']}]",
            }
        )
    else:
        results.append(
            {
                "check": "standards-verify",
                "status": "fail",
                "detail": (
                    f"hash mismatch: stored={std_result['stored_hash']}, "
                    f"computed={std_result['computed_hash']}"
                ),
            }
        )

    # Secret scan (staged)
    if _tool_available("gitleaks"):
        gitleaks_config = root / ".gitleaks.toml"
        config_args = ["-c", str(gitleaks_config)] if gitleaks_config.exists() else []
        ok, output = _run_tool(
            ["gitleaks", "protect", "--staged", *config_args], timeout=30, cwd=root
        )
        if ok:
            results.append(
                {"check": "secret-scan", "status": "pass", "detail": "no secrets detected"}
            )
        else:
            results.append({"check": "secret-scan", "status": "fail", "detail": output})
    else:
        results.append(
            {"check": "secret-scan", "status": "skip", "detail": "gitleaks not installed"}
        )

    # Ruff check
    if _tool_available("ruff"):
        ok, output = _run_tool(["ruff", "check", "src/", "tests/"], timeout=30, cwd=root)
        if ok:
            results.append({"check": "ruff-check", "status": "pass", "detail": "clean"})
        else:
            results.append({"check": "ruff-check", "status": "fail", "detail": output})
    else:
        results.append({"check": "ruff-check", "status": "skip", "detail": "ruff not installed"})

    # Precedent checks
    prec_result = check_precedents(scope="local", root=root)
    if prec_result["status"] == "pass":
        results.append(
            {"check": "precedent-check", "status": "pass", "detail": prec_result["detail"]}
        )
    elif prec_result["status"] == "warn":
        results.append(
            {
                "check": "precedent-check",
                "status": "warn",
                "detail": prec_result["summary"],
            }
        )
    else:
        hits = prec_result.get("hits", [])
        detail = " | ".join(f"{h['description']} ({h['severity']})" for h in hits if h["hit"])
        results.append({"check": "precedent-check", "status": "fail", "detail": detail})

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")
    warned = sum(1 for r in results if r["status"] == "warn")

    return json.dumps(
        {
            "all_passed": failed == 0,
            "summary": f"{passed} passed, {failed} failed, {skipped} skipped, {warned} warned",
            "results": results,
        },
        indent=2,
    )


@mcp.tool()
async def ocd_ci_check(fast: bool = False) -> str:
    """Run full local CI mirror of all quality gates.

    Args:
        fast: If True, skip full test suite (diff-aware only).
    """
    root = _find_project_root()
    results: list[dict[str, Any]] = []

    # Standards verify
    std_result = verify_standards_hash()
    results.append(
        {
            "check": "standards-verify",
            "status": "pass" if std_result["match"] else "fail",
            "detail": f"v{std_result['version']} [{std_result['computed_hash']}]",
        }
    )

    # Secret scan (full)
    if _tool_available("gitleaks"):
        gitleaks_config = root / ".gitleaks.toml"
        config_args = ["-c", str(gitleaks_config)] if gitleaks_config.exists() else []
        ok, output = _run_tool(
            ["gitleaks", "detect", "--source", ".", *config_args], timeout=60, cwd=root
        )
        results.append(
            {
                "check": "secret-scan",
                "status": "pass" if ok else "fail",
                "detail": "no secrets detected" if ok else output,
            }
        )
    else:
        results.append(
            {"check": "secret-scan", "status": "skip", "detail": "gitleaks not installed"}
        )

    # Ruff check
    if _tool_available("ruff"):
        ok, output = _run_tool(["ruff", "check", "src/", "tests/"], timeout=30, cwd=root)
        results.append(
            {
                "check": "ruff-check",
                "status": "pass" if ok else "fail",
                "detail": "clean" if ok else output,
            }
        )
    else:
        results.append({"check": "ruff-check", "status": "skip", "detail": "ruff not installed"})

    # Ruff format check
    if _tool_available("ruff"):
        ok, output = _run_tool(
            ["ruff", "format", "--check", "src/", "tests/"], timeout=30, cwd=root
        )
        results.append(
            {
                "check": "ruff-format",
                "status": "pass" if ok else "fail",
                "detail": "clean" if ok else output,
            }
        )
    else:
        results.append({"check": "ruff-format", "status": "skip", "detail": "ruff not installed"})

    # Mypy
    if _tool_available("mypy"):
        ok, output = _run_tool(["mypy", "src/ocd/", "--strict"], timeout=60, cwd=root)
        results.append(
            {
                "check": "mypy",
                "status": "pass" if ok else "fail",
                "detail": "clean" if ok else output,
            }
        )
    else:
        results.append({"check": "mypy", "status": "skip", "detail": "mypy not installed"})

    # Yamllint
    if _tool_available("yamllint"):
        ok, output = _run_tool(
            ["yamllint", "-f", "parsable", ".github/workflows/", ".yamllint"],
            timeout=15,
            cwd=root,
        )
        results.append(
            {
                "check": "yamllint",
                "status": "pass" if ok else "fail",
                "detail": "clean" if ok else output,
            }
        )
    else:
        results.append({"check": "yamllint", "status": "skip", "detail": "yamllint not installed"})

    # Pytest
    if _tool_available("pytest"):
        if fast:
            cmd = [sys.executable, "-m", "pytest", "-q"]
        else:
            cmd = [sys.executable, "-m", "pytest", "-v"]
        ok, output = _run_tool(cmd, timeout=120, cwd=root)
        results.append(
            {
                "check": "pytest",
                "status": "pass" if ok else "fail",
                "detail": "all tests passed" if ok else output,
            }
        )
    else:
        results.append({"check": "pytest", "status": "skip", "detail": "pytest not installed"})

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")

    return json.dumps(
        {
            "all_passed": failed == 0,
            "summary": f"{passed} passed, {failed} failed, {skipped} skipped",
            "results": results,
        },
        indent=2,
    )


# ── Commit verification ──────────────────────────────────────────────────────


@mcp.tool()
async def ocd_verify_commit(message: str) -> str:
    """Verify a commit message for prohibited attribution patterns.

    Args:
        message: The commit message text to check.
    """
    violations = check_message(message)
    if not violations:
        return json.dumps({"ok": True, "detail": "commit message is clean"})

    return json.dumps(
        {
            "ok": False,
            "detail": "commit message contains prohibited attribution",
            "violations": [
                {"pattern": pattern, "line": line.strip()} for pattern, line in violations
            ],
        },
        indent=2,
    )


# ── Secret scanning ──────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_scan_secrets(staged: bool = False) -> str:
    """Scan for secrets using gitleaks.

    Args:
        staged: If True, scan staged changes only. If False, scan entire source.
    """
    if not _tool_available("gitleaks"):
        return json.dumps(
            {
                "ok": True,
                "status": "skipped",
                "detail": "gitleaks not installed. Install: https://github.com/gitleaks/gitleaks",
            }
        )

    root = _find_project_root()
    gitleaks_config = root / ".gitleaks.toml"
    config_args = ["-c", str(gitleaks_config)] if gitleaks_config.exists() else []

    if staged:
        cmd = ["gitleaks", "protect", "--staged", *config_args]
    else:
        cmd = ["gitleaks", "detect", "--source", ".", *config_args]

    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode == 0:
        return json.dumps({"ok": True, "status": "clean", "detail": "no secrets detected"})

    scope = "staged changes" if staged else "source"
    return json.dumps(
        {
            "ok": False,
            "status": "secrets_found",
            "detail": f"potential secrets detected in {scope}",
        }
    )


# ── Formatters ───────────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_run_formatters() -> str:
    """Run all available formatters with auto-fix (ruff format, ruff check --fix)."""
    root = _find_project_root()
    results: list[dict[str, Any]] = []

    if _tool_available("ruff"):
        ok, output = _run_tool(["ruff", "format", "src/", "tests/"], timeout=30, cwd=root)
        results.append(
            {
                "formatter": "ruff-format",
                "status": "ok" if ok else "error",
                "detail": output if output else "formatted",
            }
        )

        ok, output = _run_tool(["ruff", "check", "--fix", "src/", "tests/"], timeout=30, cwd=root)
        results.append(
            {
                "formatter": "ruff-fix",
                "status": "ok" if ok else "error",
                "detail": output if output else "no fixes needed",
            }
        )
    else:
        results.append(
            {
                "formatter": "ruff",
                "status": "missing",
                "detail": "ruff not installed — `uv add ruff`",
            }
        )

    ran = sum(1 for r in results if r["status"] in ("ok", "error"))
    errors = sum(1 for r in results if r["status"] == "error")
    missing = sum(1 for r in results if r["status"] == "missing")

    return json.dumps(
        {
            "all_ok": errors == 0,
            "summary": f"{ran} ran, {errors} errors, {missing} skipped",
            "results": results,
        },
        indent=2,
    )


# ── Linting ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_lint_work(files: list[str]) -> str:
    """Lint specified files and report violations.

    Args:
        files: List of file paths to lint.
    """
    root = _find_project_root()
    results: list[dict[str, Any]] = []

    for file_path in files:
        ext = Path(file_path).suffix.lstrip(".")
        if not ext:
            continue

        full_path = root / file_path
        if not full_path.exists():
            results.append({"file": file_path, "status": "error", "detail": "file not found"})
            continue

        if ext == "py" and _tool_available("ruff"):
            ok, output = _run_tool(["ruff", "check", str(full_path)], timeout=10, cwd=root)
            results.append(
                {
                    "file": file_path,
                    "linter": "ruff",
                    "status": "clean" if ok else "errors",
                    "detail": output if output else "no issues",
                }
            )
        elif ext == "py" and not _tool_available("ruff"):
            results.append(
                {
                    "file": file_path,
                    "linter": "ruff",
                    "status": "missing",
                    "detail": "ruff not installed",
                }
            )

        if ext == "md" and _tool_available("mdformat"):
            ok, output = _run_tool(["mdformat", "--check", str(full_path)], timeout=10, cwd=root)
            results.append(
                {
                    "file": file_path,
                    "linter": "mdformat",
                    "status": "clean" if ok else "errors",
                    "detail": output if output else "formatted correctly",
                }
            )
        elif ext == "md" and not _tool_available("mdformat"):
            results.append(
                {
                    "file": file_path,
                    "linter": "mdformat",
                    "status": "missing",
                    "detail": "mdformat not installed",
                }
            )

    if not results:
        return json.dumps({"ok": True, "detail": "no lintable files provided"})

    error_count = sum(1 for r in results if r["status"] == "errors")
    return json.dumps(
        {
            "ok": error_count == 0,
            "summary": f"{len(results)} files checked, {error_count} with errors",
            "results": results,
        },
        indent=2,
    )


# ── Standards tools ──────────────────────────────────────────────────────────


@mcp.tool()
async def ocd_standards_verify() -> str:
    """Verify that the standards hash matches the embedded Nine Standards content."""
    result = verify_standards_hash()
    if result["match"]:
        return json.dumps(
            {
                "ok": True,
                "detail": f"hash verified: v{result['version']} [{result['computed_hash']}]",
            }
        )
    return json.dumps(
        {
            "ok": False,
            "detail": "hash mismatch",
            "stored_hash": result["stored_hash"],
            "computed_hash": result["computed_hash"],
            "version": result["version"],
        },
        indent=2,
    )


@mcp.tool()
async def ocd_standards_update() -> str:
    """Recompute and report the current standards hash.

    Since standards are embedded in the package, this verifies internal consistency
    rather than updating a filesystem file.
    """
    computed = compute_standards_hash()
    ref = get_standards_reference()
    return json.dumps(
        {
            "ok": True,
            "detail": f"standards reference: {ref}",
            "computed_hash": computed,
        }
    )


@mcp.tool()
async def ocd_standard_check(name: str) -> str:
    """Run a single named standard check.

    Args:
        name: Standard name key (e.g., 'no-dead-code', 'single-source-of-truth', etc.)
    """
    root = _find_project_root()
    checker = StandardsChecker(root)
    result = checker.run_one(name)
    return json.dumps(result, indent=2)


@mcp.tool()
async def ocd_standard_check_all() -> str:
    """Run all Nine Standards checks and return aggregated results."""
    root = _find_project_root()
    checker = StandardsChecker(root)
    result = checker.run_all()
    return json.dumps(result, indent=2)


@mcp.tool()
async def ocd_standard_list() -> str:
    """List available standard check names."""
    return json.dumps({"standards": sorted(_CHECKER_NAMES)}, indent=2)


@mcp.tool()
async def ocd_get_rules() -> str:
    """Return structured protocol rules for the OCD enforcement layer.

    Returns a JSON object describing the Nine Standards, mode definitions,
    quality gates, lifecycle gates, env vars, and tool listing.
    Agents can call this at startup to learn how the enforcement layer works.
    """
    return json.dumps(get_ocd_rules(), indent=2)


@mcp.tool()
async def ocd_validate_mcp_conventions() -> str:
    """Validate MCP tool naming conventions across the ecosystem.

    Checks that tool names follow the prefix pattern (adhd_*, ocd_*, asd_*)
    and flags tools without proper namespace prefixes.
    """
    root = _find_project_root()
    evidence: list[str] = []
    py_files = [
        p for p in root.rglob("*.py") if ".venv" not in str(p) and "__pycache__" not in str(p)
    ]

    valid_prefixes = ("adhd_", "ocd_", "asd_")
    tool_decorator_pattern = re.compile(r"@mcp\.tool\(\)")

    for fpath in py_files:
        content = None
        try:
            content = fpath.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        if not tool_decorator_pattern.search(content):
            continue

        # Find all tool function definitions
        for m in re.finditer(r"async def (\w+)\(.*\)", content):
            name = m.group(1)
            if not name.startswith(valid_prefixes):
                rel = _rel(root, fpath)
                evidence.append(
                    f"{rel}:{content[: m.start()].count(chr(10)) + 1}: "
                    f"'{name}' lacks required prefix ({', '.join(valid_prefixes)})"
                )

    status = "fail" if evidence else "pass"
    return json.dumps(
        {
            "check": "mcp-naming-conventions",
            "status": status,
            "evidence": evidence[:20],
        },
        indent=2,
    )


@mcp.tool()
async def ocd_validate_ppac_consistency() -> str:
    """Validate PPAC loop consistency across the codebase.

    Checks that Proposer, Predictor, Actor, Critic patterns are present
    and that decision loops follow the required sequence.
    """
    root = _find_project_root()
    evidence: list[str] = []

    ppac_phases = {
        "proposer": ["propose", "option", "candidate", "plan"],
        "predictor": ["predict", "limbic", "emotional", "amygdala", "hippocampal"],
        "accumulator": ["accumulate", "parietal", "evidence", "threshold"],
        "actor": ["select", "basal_ganglia", "go_pathway", "nogo_pathway", "action"],
        "critic": ["dopamine", "rpe", "reward_prediction", "outcome", "update"],
    }

    py_files = [
        p for p in root.rglob("*.py") if ".venv" not in str(p) and "__pycache__" not in str(p)
    ]

    for fpath in py_files:
        try:
            source = fpath.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        found_phases: set[str] = set()
        source_lower = source.lower()

        for phase, keywords in ppac_phases.items():
            for kw in keywords:
                if kw in source_lower:
                    found_phases.add(phase)
                    break

        # Flag files that have proposer but no critic (incomplete loop)
        if "proposer" in found_phases and "critic" not in found_phases:
            rel = _rel(root, fpath)
            evidence.append(
                f"{rel}: has Proposer patterns but no Critic/RPE — PPAC loop may be incomplete"
            )

        # Check for action without prior accumulation
        if "actor" in found_phases and "accumulator" not in found_phases:
            rel = _rel(root, fpath)
            evidence.append(
                f"{rel}: has Actor/Action patterns but no Accumulator — "
                f"decision may lack evidence gathering"
            )

    status = "warn" if evidence else "pass"
    return json.dumps(
        {
            "check": "ppac-consistency",
            "status": status,
            "evidence": evidence[:20],
        },
        indent=2,
    )


# ── Task-enforcer tools ─────────────────────────────────────────────────────


def _load_tasks_json(root: Path) -> dict[str, Any]:
    """Load tasks.json from the resolved path."""
    path = _resolve_tasks_path(root)
    if not path.exists():
        return {}
    try:
        return cast(dict[str, Any], json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return {}


@mcp.tool()
async def ocd_task_list(status: str = "", priority_min: int = 0) -> str:
    """List all tasks with optional kanban_status and priority filters.

    Args:
        status: Filter by kanban_status (ready, backlog, blocked, in_progress, done, archived).
        priority_min: Only return tasks with priority level >= this value.
    """
    root = _find_project_root()
    data = _load_tasks_json(root)
    pending = data.get("pending", [])
    completed = data.get("completed", [])

    results: list[dict[str, Any]] = []
    for t in pending:
        if not isinstance(t, dict):
            continue
        t_status = t.get("kanban_status", "backlog")
        if status and t_status != status:
            continue

        p = t.get("priority", {})
        if isinstance(p, dict):
            level = p.get("level", 3)
        else:
            level = p if isinstance(p, int) else 3
        if priority_min and level < priority_min:
            continue

        results.append(
            {
                "id": t.get("id"),
                "subject": t.get("subject"),
                "kanban_status": t_status,
                "priority_level": level,
                "done": t.get("done", False),
                "dependencies": t.get("dependencies", []),
            }
        )

    return json.dumps(
        {
            "count": len(results),
            "completed_count": len(completed),
            "total_pending": len(pending),
            "tasks": sorted(
                results,
                key=lambda r: (r["kanban_status"] != "ready", -(r["priority_level"] or 3)),
            ),
        },
        indent=2,
    )


@mcp.tool()
async def ocd_task_get(task_id: str) -> str:
    """Get a single task by ID with full details.

    Args:
        task_id: The task identifier (e.g., 'ocd-1', 'ocd-11').
    """
    root = _find_project_root()
    data = _load_tasks_json(root)

    for t in data.get("pending", []):
        if isinstance(t, dict) and t.get("id") == task_id:
            return json.dumps(t, indent=2)

    return json.dumps({"ok": False, "detail": f"task '{task_id}' not found"})


@mcp.tool()
async def ocd_task_update(task_id: str, updates: dict[str, Any]) -> str:
    """Update task fields and write back to tasks.json after validation.

    Args:
        task_id: The task identifier to update.
        updates: Dict of field names to new values (e.g., {'kanban_status': 'in_progress'}).
    """
    root = _find_project_root()
    path = _resolve_tasks_path(root)

    validation = validate_task_update(task_id, updates)
    if not validation.is_valid:
        return json.dumps(
            {
                "ok": False,
                "detail": "validation failed",
                "errors": [{"field": e.field, "message": e.message} for e in validation.errors],
            },
            indent=2,
        )

    if not path.exists():
        return json.dumps({"ok": False, "detail": "tasks.json not found"})

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return json.dumps({"ok": False, "detail": f"cannot read tasks.json: {exc}"})

    updated = False
    for t in data.get("pending", []):
        if isinstance(t, dict) and t.get("id") == task_id:
            t.update(updates)
            updated = True
            break

    if not updated:
        return json.dumps({"ok": False, "detail": f"task '{task_id}' not found"})

    path.write_text(json.dumps(data, indent=2) + "\n")
    return json.dumps({"ok": True, "detail": f"task '{task_id}' updated", "applied": updates})


@mcp.tool()
async def ocd_task_lifecycle_gate(task_id: str, target_status: str) -> str:
    """Check whether a task can transition to the target Kanban status.

    Validates the transition against lifecycle rules and runs standard
    checks appropriate for the transition.

    Args:
        task_id: The task identifier.
        target_status: The target kanban_status to validate transition to.
    """
    root = _find_project_root()
    data = _load_tasks_json(root)

    current = None
    for t in data.get("pending", []):
        if isinstance(t, dict) and t.get("id") == task_id:
            current = t
            break

    if current is None:
        return json.dumps({"ok": False, "detail": f"task '{task_id}' not found"})

    current_status = current.get("kanban_status", "backlog")

    # Valid transitions
    valid_transitions: dict[str, set[str]] = {
        "backlog": {"ready", "archived"},
        "ready": {"in_progress", "backlog", "archived"},
        "in_progress": {"done", "blocked", "ready"},
        "blocked": {"ready", "in_progress", "archived"},
        "done": {"archived"},
        "archived": set(),
    }

    allowed = valid_transitions.get(current_status, set())
    if target_status not in allowed:
        return json.dumps(
            {
                "ok": False,
                "detail": f"transition '{current_status}' → '{target_status}' is not allowed",
                "allowed_transitions": sorted(allowed),
            }
        )

    # Run appropriate gate checks per transition type
    gates_required: list[str] = []
    if target_status == "done":
        gates_required = sorted(_CHECKER_NAMES)
    elif target_status == "ready":
        gates_required = ["deterministic-ordering", "minimal-surface-area"]
    elif target_status == "in_progress":
        gates_required = ["no-dead-code", "single-source-of-truth"]

    gate_results: dict[str, str] = {}
    if gates_required:
        checker = StandardsChecker(root)
        for name in gates_required:
            r = checker.run_one(name)
            gate_results[name] = r["status"]

    blocked_by_failures = [n for n, s in gate_results.items() if s == "fail"]
    all_gates_passed = len(blocked_by_failures) == 0

    return json.dumps(
        {
            "ok": all_gates_passed,
            "task_id": task_id,
            "current_status": current_status,
            "target_status": target_status,
            "transition_allowed": True,
            "gates_required": gates_required,
            "gates_passed": all_gates_passed,
            "gate_results": gate_results,
            "blocked_by": blocked_by_failures or None,
        },
        indent=2,
    )


@mcp.tool()
async def ocd_task_claim(task_id: str = "") -> str:
    """Claim the highest-priority ready task and return a bus claim message.

    If task_id is provided, claims that specific task. Otherwise auto-selects
    the highest-priority task with status 'ready' or 'backlog'.
    Updates kanban_status to 'in_progress' in tasks.json.

    Args:
        task_id: Specific task to claim, or empty string to auto-select.
    """
    root = _find_project_root()
    data = _load_tasks_json(root)
    pending = data.get("pending", [])

    if not pending:
        return json.dumps({"ok": False, "detail": "no pending tasks"})

    completed_ids = {c.split(":")[0].strip() for c in data.get("completed", [])}

    claimable: list[tuple[int, dict[str, Any]]] = []
    for t in pending:
        if not isinstance(t, dict):
            continue
        if t.get("done"):
            continue
        status = t.get("kanban_status", "backlog")
        if status not in ("ready", "backlog"):
            continue

        deps = t.get("dependencies", [])
        if deps:
            unmet = [d for d in deps if d not in completed_ids]
            if unmet:
                continue

        p = t.get("priority", {})
        level = p.get("level", 3) if isinstance(p, dict) else (p if isinstance(p, int) else 3)
        claimable.append((level, t))

    if not claimable:
        return json.dumps(
            {
                "ok": False,
                "detail": (
                    "no claimable tasks — all are done, in_progress, "
                    "blocked, or have unmet dependencies"
                ),
            }
        )

    if task_id:
        matches = [(lvl, t) for lvl, t in claimable if t.get("id") == task_id]
        if not matches:
            return json.dumps(
                {"ok": False, "detail": f"task '{task_id}' not found or not claimable"}
            )
        _, selected = matches[0]
    else:
        claimable.sort(key=lambda x: (x[0], x[1].get("id", "")))
        _, selected = claimable[0]

    tid = selected["id"]
    repo = data.get("meta", {}).get("repository", root.name)

    selected["kanban_status"] = "in_progress"

    path = _resolve_tasks_path(root)
    path.write_text(json.dumps(data, indent=2) + "\n")

    claim_msg = {
        "type": "status",
        "topic": "agent-claim",
        "payload": {
            "task": tid,
            "claimed_by": "<agent_id>",
            "repo": repo,
        },
    }

    priority = selected.get("priority", {})
    level = priority.get("level", 3) if isinstance(priority, dict) else priority

    return json.dumps(
        {
            "ok": True,
            "detail": f"task '{tid}' claimed — post the bus_message via adhd_post",
            "claimed_task": {
                "id": tid,
                "subject": selected.get("subject"),
                "priority_level": level,
            },
            "bus_message": claim_msg,
        },
        indent=2,
    )


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
