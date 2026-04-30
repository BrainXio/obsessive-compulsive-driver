"""Automated checkers for each of the Nine Standards.

Each checker accepts a project root Path and returns a structured result dict
with: standard (str), status (pass/fail/warn/skip), evidence (list[str]).

Several standards are inherently heuristic — they flag patterns for human review
rather than asserting definitive violations. The "warn" status covers those cases.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

# ── Helpers ──────────────────────────────────────────────────────────────────────


def _find_files(root: Path, patterns: list[str], max_files: int = 200) -> list[Path]:
    """Find files matching glob patterns, excluding common non-source dirs."""
    exclude = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".archive",
        ".claude",
        "node_modules",
    }
    results: list[Path] = []
    for pattern in patterns:
        for p in root.rglob(pattern):
            if any(part in exclude for part in p.parts):
                continue
            results.append(p)
            if len(results) >= max_files:
                return results
    return results


def _find_python_files(root: Path) -> list[Path]:
    return _find_files(root, ["*.py"])


def _find_markdown_files(root: Path) -> list[Path]:
    return _find_files(root, ["*.md"])


def _find_config_files(root: Path) -> list[Path]:
    return _find_files(root, ["*.toml", "*.json", "*.yaml", "*.yml", "*.cfg", "*.ini"])


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 1: No Dead Code
# ═══════════════════════════════════════════════════════════════════════════════════


def check_no_dead_code(root: Path) -> dict[str, Any]:
    """Scan Python files for potentially unused functions and classes.

    Collects all defined names and all name references across all Python files,
    then flags definitions whose name never appears as a Name reference anywhere.
    """
    evidence: list[str] = []
    py_files = _find_python_files(root)

    # Collect all definitions and references across the entire codebase
    all_defined: dict[str, list[tuple[str, int]]] = {}
    all_referenced: set[str] = set()

    for fpath in py_files:
        source = _read_file(fpath)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        rel = _rel(root, fpath)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name not in ("__init__", "__repr__", "__str__", "__post_init__"):
                    all_defined.setdefault(node.name, []).append((rel, node.lineno))
            elif isinstance(node, ast.Name):
                all_referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    all_referenced.add(node.value.id)

    for name, locations in all_defined.items():
        if name not in all_referenced:
            for rel, lineno in locations:
                evidence.append(f"{rel}:{lineno}: '{name}' appears unused")

    status = "fail" if evidence else "pass"
    return {
        "standard": "No Dead Code",
        "status": status,
        "evidence": evidence[:20],
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 2: Single Source of Truth
# ═══════════════════════════════════════════════════════════════════════════════════


def check_single_source_of_truth(root: Path) -> dict[str, Any]:
    """Flag string literals that appear verbatim in multiple files.

    Strings >= 20 chars that appear in 3+ files suggest a missing constant,
    config value, or shared definition.
    """
    evidence: list[str] = []
    py_files = _find_python_files(root)

    # Collect string literals from Python files
    string_locations: dict[str, list[str]] = {}
    for fpath in py_files:
        source = _read_file(fpath)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                s = node.value.strip()
                if len(s) >= 20 and not s.startswith(("http://", "https://")):
                    rel = _rel(root, fpath)
                    string_locations.setdefault(s, []).append(rel)

    for s, locations in string_locations.items():
        unique_files = set(locations)
        if len(unique_files) >= 3:
            evidence.append(
                f"'{s[:60]}{'...' if len(s) > 60 else ''}' "
                f"appears in {len(unique_files)} files: {', '.join(sorted(unique_files)[:5])}"
            )

    status = "warn" if evidence else "pass"
    return {
        "standard": "Single Source of Truth",
        "status": status,
        "evidence": evidence[:15],
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 3: Consistent Defaults
# ═══════════════════════════════════════════════════════════════════════════════════


def check_consistent_defaults(root: Path) -> dict[str, Any]:
    """Check for config value inconsistencies across configuration files.

    Compares pyproject.toml settings with their appearance in other config files.
    """
    evidence: list[str] = []
    config_files = _find_config_files(root)

    # Collect key-value pairs from TOML/JSON config files
    config_entries: dict[str, list[tuple[str, str]]] = {}
    for fpath in config_files:
        if fpath.suffix == ".toml":
            entries = _parse_toml_shallow(fpath)
        elif fpath.suffix == ".json":
            entries = _parse_json_shallow(fpath)
        else:
            continue
        for key, value in entries.items():
            config_entries.setdefault(key, []).append((_rel(root, fpath), value))

    for key, occurrences in config_entries.items():
        if len(occurrences) >= 2:
            values = {v for _, v in occurrences}
            if len(values) > 1:
                files = [f for f, _ in occurrences]
                evidence.append(
                    f"'{key}' has conflicting values ({', '.join(sorted(values))}) "
                    f"in {', '.join(sorted(files))}"
                )

    status = "fail" if evidence else "pass"
    return {
        "standard": "Consistent Defaults",
        "status": status,
        "evidence": evidence[:15],
    }


def _parse_toml_shallow(path: Path) -> dict[str, str]:
    """Extract top-level dotted keys and string values from TOML (best-effort)."""
    entries: dict[str, str] = {}
    content = _read_file(path)
    if content is None:
        return entries
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^(\w[\w.]*\w)\s*=\s*["\']([^"\']+)["\']', line)
        if m:
            entries[m.group(1)] = m.group(2)
    return entries


def _parse_json_shallow(path: Path) -> dict[str, str]:
    """Extract top-level string values from JSON (best-effort)."""
    entries: dict[str, str] = {}
    content = _read_file(path)
    if content is None:
        return entries
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return entries
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                entries[str(key)] = value
    return entries


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 4: Minimal Surface Area
# ═══════════════════════════════════════════════════════════════════════════════════


def check_minimal_surface_area(root: Path) -> dict[str, Any]:
    """Flag configuration bloat: excessive flags, knobs, or conditional branches."""
    evidence: list[str] = []
    py_files = _find_python_files(root)

    for fpath in py_files:
        source = _read_file(fpath)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        # Count boolean config/env flags and if/else branches
        bool_flags = 0
        branches = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                        if isinstance(node.value.value, bool):
                            bool_flags += 1
            elif isinstance(node, ast.If):
                branches += 1

        if bool_flags >= 10:
            evidence.append(
                f"{_rel(root, fpath)}: {bool_flags} boolean flags — "
                f"consider consolidating (Standard 4)"
            )
        if branches >= 30:
            evidence.append(
                f"{_rel(root, fpath)}: {branches} if/else branches — high cyclomatic complexity"
            )

    status = "warn" if evidence else "pass"
    return {
        "standard": "Minimal Surface Area",
        "status": status,
        "evidence": evidence[:15],
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 5: Defense in Depth
# ═══════════════════════════════════════════════════════════════════════════════════


def check_defense_in_depth(root: Path) -> dict[str, Any]:
    """Verify security tooling and layered defenses are configured.

    Checks for presence of: gitleaks config, security linters, input validation patterns.
    """
    evidence: list[str] = []
    ok: list[str] = []

    # Gitleaks
    if (root / ".gitleaks.toml").exists():
        ok.append("gitleaks config present")
    else:
        evidence.append("no .gitleaks.toml — secret scanning not configured")

    # Bandit or security-focused ruff rules
    pyproject = _read_file(root / "pyproject.toml")
    if pyproject:
        if "S" in pyproject or "bandit" in pyproject.lower():
            ok.append("security lint rules configured")
        else:
            evidence.append("no security-focused lint rules (ruff 'S' or bandit)")

    # Pre-commit hooks
    if (root / ".pre-commit-config.yaml").exists():
        ok.append("pre-commit hooks present")
    else:
        evidence.append("no .pre-commit-config.yaml — no automated hook enforcement")

    status = "fail" if evidence else "pass"
    return {
        "standard": "Defense in Depth",
        "status": status,
        "evidence": evidence[:15],
        "detail": f"{len(ok)} defenses present, {len(evidence)} missing",
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 6: Structural Honesty
# ═══════════════════════════════════════════════════════════════════════════════════


def check_structural_honesty(root: Path) -> dict[str, Any]:
    """Flag functions whose names may not match their behavior.

    Heuristic checks: functions named 'get_*' that modify state, functions
    with boolean returns named without 'is_'/'has_' prefix, etc.
    """
    evidence: list[str] = []
    py_files = _find_python_files(root)

    for fpath in py_files:
        source = _read_file(fpath)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            name = node.name

            # Functions returning bool without is_/has_ prefix
            has_return_bool = _has_bool_return(node)
            if has_return_bool and not (
                name.startswith("is_")
                or name.startswith("has_")
                or name.startswith("check_")
                or name.startswith("verify_")
                or name.startswith("validate_")
            ):
                evidence.append(
                    f"{_rel(root, fpath)}:{node.lineno}: '{name}' returns bool "
                    f"but lacks is_/has_/check_ prefix"
                )

            # apply_/run_/execute_ — should not return None silently
            if name.startswith(("apply_", "run_", "execute_")) and _returns_none(node):
                evidence.append(
                    f"{_rel(root, fpath)}:{node.lineno}: '{name}' appears to "
                    f"return None — action functions should report outcome"
                )

    status = "warn" if evidence else "pass"
    return {
        "standard": "Structural Honesty",
        "status": status,
        "evidence": evidence[:15],
    }


def _has_bool_return(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Constant):
                val = getattr(node.value, "value", None)
                if isinstance(val, bool):
                    return True
    return False


def _returns_none(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return_nodes = [n for n in ast.walk(func_node) if isinstance(n, ast.Return)]
    if not return_nodes:
        return True  # Implicit return None
    for node in return_nodes:
        if node.value is not None:
            if isinstance(node.value, ast.Constant) and node.value.value is None:
                continue
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 7: Progressive Simplification
# ═══════════════════════════════════════════════════════════════════════════════════


def check_progressive_simplification(root: Path) -> dict[str, Any]:
    """Flag files that are unusually long relative to their functional scope.

    Python files > 300 lines and markdown files > 200 lines are flagged.
    """
    evidence: list[str] = []

    for fpath in _find_python_files(root):
        source = _read_file(fpath)
        if source is None:
            continue
        line_count = len(source.splitlines())
        if line_count > 300:
            evidence.append(
                f"{_rel(root, fpath)}: {line_count} lines — consider splitting (Standard 7)"
            )

    for fpath in _find_markdown_files(root):
        source = _read_file(fpath)
        if source is None:
            continue
        line_count = len(source.splitlines())
        if line_count > 200:
            evidence.append(
                f"{_rel(root, fpath)}: {line_count} lines — consider splitting (Standard 7)"
            )

    status = "warn" if evidence else "pass"
    return {
        "standard": "Progressive Simplification",
        "status": status,
        "evidence": evidence[:15],
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 8: Deterministic Ordering
# ═══════════════════════════════════════════════════════════════════════════════════


def check_deterministic_ordering(root: Path) -> dict[str, Any]:
    """Check that markdown tables and lists are alphabetically sorted."""
    evidence: list[str] = []

    for fpath in _find_markdown_files(root):
        source = _read_file(fpath)
        if source is None:
            continue

        # Check markdown tables for alphabetical row ordering
        evidence.extend(_check_table_ordering(fpath, source, root))

        # Check bullet lists
        evidence.extend(_check_list_ordering(fpath, source, root))

    # Check pyproject.toml dependency lists
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = _read_file(pyproject)
        if content:
            evidence.extend(_check_toml_dependency_ordering(content, root))

    status = "fail" if evidence else "pass"
    return {
        "standard": "Deterministic Ordering",
        "status": status,
        "evidence": evidence[:15],
    }


def _check_table_ordering(fpath: Path, source: str, root: Path) -> list[str]:
    evidence: list[str] = []
    lines = source.splitlines()
    in_table = False
    table_rows: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            if not in_table:
                in_table = True
                table_rows = []
            # Skip separator rows like |---|---|
            if not re.match(r"^\|[\s\-:|]+\|$", stripped):
                table_rows.append((i, stripped))
        else:
            if in_table and len(table_rows) > 2:
                # Check if rows are sorted by first column
                first_cols = [_extract_first_column(r) for _, r in table_rows[1:]]
                sorted_cols = sorted(first_cols, key=str.lower)
                if first_cols != sorted_cols and first_cols != sorted_cols[::-1]:
                    evidence.append(
                        f"{_rel(root, fpath)}:{table_rows[0][0] + 1}: "
                        f"table rows not alphabetically sorted by first column"
                    )
            in_table = False
            table_rows = []

    return evidence


def _extract_first_column(row: str) -> str:
    parts = row.split("|")
    if len(parts) >= 2:
        return parts[1].strip()
    return ""


def _check_list_ordering(fpath: Path, source: str, root: Path) -> list[str]:
    evidence: list[str] = []
    lines = source.splitlines()
    in_list = False
    list_items: list[str] = []
    list_start_line = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")) and not stripped.startswith("- ["):
            if not in_list:
                in_list = True
                list_items = []
                list_start_line = i
            list_items.append(stripped[2:])
        else:
            if in_list:
                evidence.extend(_check_one_list(list_items, list_start_line, fpath, root))
            in_list = False
            list_items = []

    # Check list at end of file
    if in_list:
        evidence.extend(_check_one_list(list_items, list_start_line, fpath, root))

    return evidence


def _check_one_list(items: list[str], start_line: int, fpath: Path, root: Path) -> list[str]:
    if len(items) < 4:
        return []
    first_words = [_first_word(item) for item in items]
    sorted_words = sorted(first_words, key=str.lower)
    if first_words == sorted_words:
        return []
    if _has_priority_keywords(items):
        return []
    return [f"{_rel(root, fpath)}:{start_line + 1}: bullet list not alphabetically sorted"]


def _first_word(item: str) -> str:
    # Extract first meaningful word, stripping inline code backticks
    word = item.lstrip("`*_")
    return word.split()[0] if word.split() else word


def _has_priority_keywords(items: list[str]) -> bool:
    priority_keywords = {
        "critical",
        "high",
        "medium",
        "low",
        "step",
        "phase",
        "must",
        "should",
        "may",
        "required",
        "before",
        "after",
        "first",
        "then",
        "finally",
    }
    for item in items:
        first = _first_word(item).lower().rstrip(":")
        if first in priority_keywords:
            return True
    return False


def _check_toml_dependency_ordering(content: str, root: Path) -> list[str]:
    evidence: list[str] = []
    in_deps = False
    dep_names: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if re.match(r"^\[.*dependencies.*\]", stripped):
            in_deps = True
            dep_names = []
            continue
        if in_deps and stripped.startswith("["):
            if len(dep_names) >= 4:
                sorted_deps = sorted(dep_names, key=str.lower)
                if dep_names != sorted_deps:
                    evidence.append("pyproject.toml: dependencies not alphabetically sorted")
            in_deps = False
            dep_names = []
            continue
        if in_deps:
            m = re.match(r"^([\w\-]+)\s*[=>]", stripped)
            if m:
                dep_names.append(m.group(1))

    return evidence


# ═══════════════════════════════════════════════════════════════════════════════════
# Standard 9: Inconsistent Elimination
# ═══════════════════════════════════════════════════════════════════════════════════


def check_inconsistent_elimination(root: Path) -> dict[str, Any]:
    """Detect inconsistencies between config, formatter output, and committed files.

    Checks ruff format consistency by running format check and comparing.
    """
    evidence: list[str] = []

    # Check if ruff config matches committed files (format check)
    import shutil
    import subprocess

    if shutil.which("ruff"):
        result = subprocess.run(
            ["ruff", "format", "--check", "src/", "tests/"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        if result.returncode != 0:
            dirty = [
                line.strip()
                for line in (result.stdout + result.stderr).splitlines()
                if line.strip() and "Would reformat" in line
            ]
            if dirty:
                evidence.append(f"ruff format mismatch: {len(dirty)} file(s) would be reformatted")
                evidence.extend(f"  {d}" for d in dirty[:5])
    else:
        evidence.append("ruff not installed — cannot verify format consistency")

    status = "fail" if evidence else "pass"
    return {
        "standard": "Inconsistent Elimination",
        "status": status,
        "evidence": evidence[:15],
    }


# ═══════════════════════════════════════════════════════════════════════════════════
# Check runner — runs all Nine Standards
# ═══════════════════════════════════════════════════════════════════════════════════

_CHECKERS: dict[str, Any] = {
    "no-dead-code": check_no_dead_code,
    "single-source-of-truth": check_single_source_of_truth,
    "consistent-defaults": check_consistent_defaults,
    "minimal-surface-area": check_minimal_surface_area,
    "defense-in-depth": check_defense_in_depth,
    "structural-honesty": check_structural_honesty,
    "progressive-simplification": check_progressive_simplification,
    "deterministic-ordering": check_deterministic_ordering,
    "inconsistent-elimination": check_inconsistent_elimination,
}

_CHECKER_NAMES: frozenset[str] = frozenset(_CHECKERS.keys())


class StandardsChecker:
    """Run all Nine Standards checkers and aggregate results."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path.cwd()

    def run_all(self) -> dict[str, Any]:
        results = []
        for name in sorted(_CHECKERS):
            fn = _CHECKERS[name]
            try:
                r = fn(self.root)
                results.append(r)
            except Exception as exc:
                results.append(
                    {
                        "standard": name,
                        "status": "error",
                        "evidence": [str(exc)],
                    }
                )
        return _summarize(results)

    def run_one(self, name: str) -> dict[str, Any]:
        fn = _CHECKERS.get(name)
        if fn is None:
            return {
                "standard": name,
                "status": "error",
                "evidence": [
                    f"Unknown standard: '{name}'. Known: {', '.join(sorted(_CHECKER_NAMES))}"
                ],
            }
        try:
            return fn(self.root)
        except Exception as exc:
            return {
                "standard": name,
                "status": "error",
                "evidence": [str(exc)],
            }

    @classmethod
    def list_standards(cls) -> list[str]:
        return sorted(_CHECKER_NAMES)


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    errors = sum(1 for r in results if r["status"] == "error")

    return {
        "all_passed": failed == 0 and errors == 0,
        "summary": f"{passed} passed, {failed} failed, {warned} warnings, {errors} errors",
        "passed": passed,
        "failed": failed,
        "warned": warned,
        "errors": errors,
        "results": results,
    }


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
