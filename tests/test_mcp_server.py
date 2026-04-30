"""Tests for OCD MCP server tools."""

from __future__ import annotations

import json

import pytest

from ocd.mcp_server import (
    ocd_check,
    ocd_ci_check,
    ocd_get_mode,
    ocd_lint_work,
    ocd_run_formatters,
    ocd_scan_secrets,
    ocd_set_mode,
    ocd_standards_update,
    ocd_standards_verify,
    ocd_verify_commit,
)
from ocd.standards_data import (
    check_message,
    compute_hash,
    get_standards_reference,
    verify_standards_hash,
)

# ── Mode tools ────────────────────────────────────────────────────────────────


class TestModeTools:
    async def test_set_mode_valid(self) -> None:
        result = json.loads(await ocd_set_mode("developer"))
        assert result["ok"] is True
        assert result["mode"] == "developer"

    async def test_set_mode_invalid(self) -> None:
        result = json.loads(await ocd_set_mode("bogus-mode"))
        assert result["ok"] is False
        assert "Unknown mode" in result["error"]

    async def test_get_mode_default(self) -> None:
        result = json.loads(await ocd_get_mode())
        assert "mode" in result


# ── Standards tools ──────────────────────────────────────────────────────────


class TestStandardsTools:
    async def test_standards_verify(self) -> None:
        result = json.loads(await ocd_standards_verify())
        assert result["ok"] is True
        assert "hash verified" in result["detail"]

    async def test_standards_update(self) -> None:
        result = json.loads(await ocd_standards_update())
        assert result["ok"] is True
        assert "computed_hash" in result

    def test_hash_consistency(self) -> None:
        stored = verify_standards_hash()
        assert stored["match"] is True, (
            f"Hash mismatch: stored={stored['stored_hash']}, computed={stored['computed_hash']}"
        )

    def test_reference_format(self) -> None:
        ref = get_standards_reference()
        assert ref.startswith("ocd-standards:v")
        assert "[" in ref
        assert "]" in ref


# ── Commit verification ──────────────────────────────────────────────────────


class TestVerifyCommit:
    async def test_clean_message(self) -> None:
        result = json.loads(await ocd_verify_commit("feat: add new feature"))
        assert result["ok"] is True
        assert result["detail"] == "commit message is clean"

    async def test_co_author_blocked(self) -> None:
        msg = "feat: add feature\n\nCo-Authored-By: Someone <someone@example.com>"
        result = json.loads(await ocd_verify_commit(msg))
        assert result["ok"] is False
        assert "violations" in result

    async def test_generated_by_blocked(self) -> None:
        result = json.loads(await ocd_verify_commit("fix: bug\n\nGenerated with tool"))
        assert result["ok"] is False

    async def test_ai_tag_blocked(self) -> None:
        result = json.loads(await ocd_verify_commit("[AI] add feature"))
        assert result["ok"] is False

    async def test_clean_conventional_commit(self) -> None:
        msg = "feat(hooks): add post-merge hook for dependency sync"
        result = json.loads(await ocd_verify_commit(msg))
        assert result["ok"] is True


# ── Check tools ───────────────────────────────────────────────────────────────


class TestCheck:
    async def test_check_returns_structured_result(self) -> None:
        result = json.loads(await ocd_check())
        assert "all_passed" in result
        assert "summary" in result
        assert "results" in result
        assert isinstance(result["results"], list)

    async def test_check_standards_included(self) -> None:
        result = json.loads(await ocd_check())
        checks = [r["check"] for r in result["results"]]
        assert "standards-verify" in checks
        assert "branch-protection" in checks


class TestCiCheck:
    async def test_ci_check_returns_structured_result(self) -> None:
        result = json.loads(await ocd_ci_check(fast=True))
        assert "all_passed" in result
        assert "summary" in result
        assert "results" in result

    async def test_ci_check_includes_standards(self) -> None:
        result = json.loads(await ocd_ci_check(fast=True))
        checks = [r["check"] for r in result["results"]]
        assert "standards-verify" in checks


# ── Secret scanning ──────────────────────────────────────────────────────────


class TestScanSecrets:
    async def test_scan_secrets_returns_result(self) -> None:
        result = json.loads(await ocd_scan_secrets(staged=False))
        assert "status" in result
        assert result["status"] in ("clean", "skipped", "secrets_found")


# ── Formatters ───────────────────────────────────────────────────────────────


class TestFormatters:
    async def test_run_formatters_returns_result(self) -> None:
        result = json.loads(await ocd_run_formatters())
        assert "all_ok" in result
        assert "results" in result
        assert isinstance(result["results"], list)


# ── Linting ──────────────────────────────────────────────────────────────────


class TestLintWork:
    async def test_lint_empty_files(self) -> None:
        result = json.loads(await ocd_lint_work([]))
        assert result["ok"] is True
        assert "no lintable files" in result["detail"]

    async def test_lint_unknown_extension(self) -> None:
        result = json.loads(await ocd_lint_work(["image.png"]))
        assert result["ok"] is True

    async def test_lint_missing_file(self) -> None:
        result = json.loads(await ocd_lint_work(["nonexistent.py"]))
        assert result["ok"] is True


# ── Standards data unit tests ────────────────────────────────────────────────


class TestStandardsData:
    def test_hash_deterministic(self) -> None:
        h1 = compute_hash("test")
        h2 = compute_hash("test")
        assert h1 == h2

    def test_hash_different_content(self) -> None:
        h1 = compute_hash("test1")
        h2 = compute_hash("test2")
        assert h1 != h2

    def test_check_message_empty(self) -> None:
        violations = check_message("")
        assert len(violations) == 0

    def test_check_message_none(self) -> None:
        violations = check_message("no patterns here")
        assert len(violations) == 0


# ── Integration-style tests ──────────────────────────────────────────────────


class TestToolResponseFormat:
    """Verify all tools return valid JSON."""

    TOOLS = [
        (ocd_get_mode, {}),
        (ocd_set_mode, {"mode": "developer"}),
        (ocd_standards_verify, {}),
        (ocd_standards_update, {}),
        (ocd_verify_commit, {"message": "feat: test"}),
        (ocd_scan_secrets, {}),
        (ocd_run_formatters, {}),
    ]

    @pytest.mark.parametrize("tool_fn,kwargs", TOOLS)
    async def test_tool_returns_valid_json(self, tool_fn, kwargs) -> None:
        result = await tool_fn(**kwargs)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
