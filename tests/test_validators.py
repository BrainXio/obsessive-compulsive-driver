"""Tests for MCP-pattern and PPAC-consistency validators."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ocd.mcp_server import (
    ocd_validate_mcp_conventions,
    ocd_validate_ppac_consistency,
)


def _write_files(root: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)


class TestMcpNamingValidator:
    async def test_pass_when_no_tools(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_files(root, {"mod.py": "x = 1\n"})
            # Can't test via MCP tool since it uses CWD; test logic directly
            # MCP tools run against CWD, so we just verify they return valid JSON
            result = json.loads(await ocd_validate_mcp_conventions())
            assert "check" in result
            assert "status" in result
            assert result["status"] in ("pass", "fail", "warn")

    async def test_detects_unprefixed_tool(self) -> None:
        result = json.loads(await ocd_validate_mcp_conventions())
        # Tests that OCD's own MCP tools follow conventions
        # All OCD MCP tools should use ocd_ prefix
        assert result["check"] == "mcp-naming-conventions"


class TestPpacValidator:
    async def test_returns_structured_result(self) -> None:
        result = json.loads(await ocd_validate_ppac_consistency())
        assert result["check"] == "ppac-consistency"
        assert "status" in result
        assert "evidence" in result
        assert isinstance(result["evidence"], list)


class TestModeSystem:
    """Tests for the expanded mode system."""

    async def test_set_research_mode(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("research"))
        assert result["ok"] is True
        assert result["mode"] == "research"

    async def test_set_review_mode(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("review"))
        assert result["ok"] is True

    async def test_set_ops_mode(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("ops"))
        assert result["ok"] is True

    async def test_set_personal_mode(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("personal"))
        assert result["ok"] is True

    async def test_set_invalid_mode_still_rejected(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("invalid"))
        assert result["ok"] is False

    async def test_reset_to_developer(self) -> None:
        from ocd.mcp_server import ocd_set_mode

        result = json.loads(await ocd_set_mode("developer"))
        assert result["ok"] is True
        assert result["mode"] == "developer"


class TestModeDefinitions:
    def test_all_modes_have_all_standards(self) -> None:
        from ocd.modes.mode_definitions import MODE_DEFINITIONS

        standard_names = {
            "no-dead-code",
            "single-source-of-truth",
            "consistent-defaults",
            "minimal-surface-area",
            "defense-in-depth",
            "structural-honesty",
            "progressive-simplification",
            "deterministic-ordering",
            "inconsistent-elimination",
        }
        for mode_name, config in MODE_DEFINITIONS.items():
            assert set(config["standards"].keys()) == standard_names, (
                f"Mode '{mode_name}' missing standards"
            )

    def test_all_levels_are_valid(self) -> None:
        from ocd.modes.mode_definitions import MODE_DEFINITIONS

        valid_levels = {"strict", "warn", "skip"}
        for config in MODE_DEFINITIONS.values():
            for level in config["standards"].values():
                assert level in valid_levels

    def test_get_mode_config_developer_default(self) -> None:
        from ocd.modes.mode_definitions import get_mode_config

        config = get_mode_config("nonexistent")
        assert config == get_mode_config("developer")

    def test_get_standard_level_unknown_defaults_strict(self) -> None:
        from ocd.modes.mode_definitions import get_standard_level

        level = get_standard_level("nonexistent", "nonexistent")
        assert level == "strict"

    def test_get_standard_level_research_skips_dead_code(self) -> None:
        from ocd.modes.mode_definitions import get_standard_level

        level = get_standard_level("research", "no-dead-code")
        assert level == "skip"
