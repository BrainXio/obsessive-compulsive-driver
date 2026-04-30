"""Tests for OCD standards checkers."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ocd.mcp_server import (
    ocd_standard_check,
    ocd_standard_check_all,
    ocd_standard_list,
)
from ocd.tools.standards_checker import (
    StandardsChecker,
    check_defense_in_depth,
    check_deterministic_ordering,
    check_minimal_surface_area,
    check_no_dead_code,
    check_progressive_simplification,
    check_single_source_of_truth,
    check_structural_honesty,
)


def _write_files(root: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)


class TestNoDeadCode:
    def test_pass_on_empty_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            result = check_no_dead_code(Path(tmp))
            assert result["status"] == "pass"

    def test_fail_on_unused_function(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "mod.py": "def unused_fn():\n    pass\n",
                },
            )
            result = check_no_dead_code(root)
            # unused_fn only appears in its definition
            assert result["status"] in ("fail", "warn")

    def test_pass_on_used_function(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "mod.py": ("def used_fn():\n    return 1\n\nresult = used_fn()\n"),
                },
            )
            result = check_no_dead_code(root)
            # Function is used in the same file, should pass
            assert result["status"] == "pass"

    def test_skip_dunder_methods(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "mod.py": (
                        "class Foo:\n"
                        "    def __init__(self):\n        pass\n"
                        "    def __repr__(self):\n        return 'Foo'\n"
                    ),
                },
            )
            result = check_no_dead_code(root)
            # class Foo is unused (flagged), but dunder methods are excluded
            assert any("Foo" in e for e in result["evidence"])
            assert not any("__init__" in e for e in result["evidence"])
            assert not any("__repr__" in e for e in result["evidence"])


class TestSingleSourceOfTruth:
    def test_pass_on_unique_strings(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "a.py": "x = 'short'\n",
                    "b.py": "y = 'different unique string'\n",
                },
            )
            result = check_single_source_of_truth(root)
            assert result["status"] == "pass"

    def test_skip_urls(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "a.py": "URL = 'https://example.com/api/v1/very/long/path'\n",
                    "b.py": "OTHER = 'https://example.com/api/v1/very/long/path'\n",
                    "c.py": "THIRD = 'https://example.com/api/v1/very/long/path'\n",
                },
            )
            result = check_single_source_of_truth(root)
            # URLs are excluded
            assert result["status"] == "pass"


class TestDeterministicOrdering:
    def test_pass_on_empty_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            result = check_deterministic_ordering(Path(tmp))
            assert result["status"] == "pass"

    def test_flag_unsorted_bullet_list(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "unsorted.md": ("- zebra item\n- apple item\n- middle item\n- delta item\n"),
                },
            )
            result = check_deterministic_ordering(root)
            assert result["status"] == "fail"


class TestMinimalSurfaceArea:
    def test_pass_on_small_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(root, {"mod.py": "x = 1\n"})
            result = check_minimal_surface_area(root)
            assert result["status"] == "pass"


class TestProgressiveSimplification:
    def test_pass_on_short_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(root, {"mod.py": "x = 1\ny = 2\n"})
            result = check_progressive_simplification(root)
            assert result["status"] == "pass"


class TestDefenseInDepth:
    def test_returns_structured_result(self) -> None:
        with TemporaryDirectory() as tmp:
            result = check_defense_in_depth(Path(tmp))
            assert result["standard"] == "Defense in Depth"
            assert result["status"] in ("pass", "fail", "warn", "skip")


class TestStructuralHonesty:
    def test_flag_bool_return_without_is_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "mod.py": "def ready():\n    return True\n",
                },
            )
            result = check_structural_honesty(root)
            # 'ready' returns bool but lacks is_ prefix
            assert result["status"] in ("warn", "fail")

    def test_pass_on_proper_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(
                root,
                {
                    "mod.py": "def is_ready():\n    return True\n",
                },
            )
            result = check_structural_honesty(root)
            assert result["status"] == "pass"


class TestStandardsChecker:
    def test_run_all_returns_all_standards(self) -> None:
        with TemporaryDirectory() as tmp:
            checker = StandardsChecker(Path(tmp))
            result = checker.run_all()
            assert "results" in result
            assert len(result["results"]) == 9
            names = {r["standard"] for r in result["results"]}
            assert "No Dead Code" in names
            assert "Deterministic Ordering" in names

    def test_run_one_known_standard(self) -> None:
        with TemporaryDirectory() as tmp:
            checker = StandardsChecker(Path(tmp))
            result = checker.run_one("no-dead-code")
            assert result["standard"] == "No Dead Code"

    def test_run_one_unknown_standard(self) -> None:
        with TemporaryDirectory() as tmp:
            checker = StandardsChecker(Path(tmp))
            result = checker.run_one("nonexistent")
            assert result["status"] == "error"

    def test_list_standards(self) -> None:
        standards = StandardsChecker.list_standards()
        assert len(standards) == 9
        assert "no-dead-code" in standards
        assert standards == sorted(standards)


# ── MCP tool integration tests ───────────────────────────────────────────────


class TestMcpStandardTools:
    async def test_standard_check_all(self) -> None:
        result = json.loads(await ocd_standard_check_all())
        assert "results" in result
        assert len(result["results"]) == 9

    async def test_standard_check_one(self) -> None:
        result = json.loads(await ocd_standard_check("defense-in-depth"))
        assert result["standard"] == "Defense in Depth"

    async def test_standard_check_unknown(self) -> None:
        result = json.loads(await ocd_standard_check("nope"))
        assert result["status"] == "error"

    async def test_standard_list(self) -> None:
        result = json.loads(await ocd_standard_list())
        assert "standards" in result
        assert len(result["standards"]) == 9

    async def test_standard_list_sorted(self) -> None:
        result = json.loads(await ocd_standard_list())
        assert result["standards"] == sorted(result["standards"])
