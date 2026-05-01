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
    ocd_task_claim,
    ocd_task_get,
    ocd_task_lifecycle_gate,
    ocd_task_list,
    ocd_task_update,
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

    TOOLS_EXTENDED = [
        (ocd_get_mode, {}),
        (ocd_set_mode, {"mode": "developer"}),
        (ocd_standards_verify, {}),
        (ocd_standards_update, {}),
        (ocd_verify_commit, {"message": "feat: test"}),
        (ocd_scan_secrets, {}),
        (ocd_run_formatters, {}),
        (ocd_get_mode, {}),
    ]

    @pytest.mark.parametrize("tool_fn,kwargs", TOOLS)
    async def test_tool_returns_valid_json(self, tool_fn, kwargs) -> None:
        result = await tool_fn(**kwargs)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)


# ── get_rules tests ───────────────────────────────────────────────────────


class TestGetRules:
    async def test_ocd_get_rules_returns_structured_json(self) -> None:
        from ocd.mcp_server import ocd_get_rules

        result = json.loads(await ocd_get_rules())
        assert result["package"] == "ocd"
        assert "version" in result
        assert "nine_standards" in result
        assert "modes" in result
        assert "quality_gates" in result
        assert "lifecycle_gates" in result
        assert "tools" in result

    def test_get_rules_function_from_rules_module(self) -> None:
        from ocd.rules import get_rules

        rules = get_rules()
        assert rules["package"] == "ocd"
        assert isinstance(rules["modes"], list)
        assert len(rules["modes"]) >= 1
        assert rules["nine_standards"]["checks"][0]["name"] == "no-dead-code"
        assert isinstance(rules["tools"], list)
        assert len(rules["tools"]) >= 10


# ── Task-enforcer tools ───────────────────────────────────────────────────────


def _mock_project_root():
    return __import__("pathlib").Path("/tmp")


class TestTaskList:
    """Tests for ocd_task_list MCP tool."""

    async def test_task_list_returns_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {"id": "ocd-1", "subject": "first", "kanban_status": "ready", "priority": 1},
                    {"id": "ocd-2", "subject": "second", "kanban_status": "backlog", "priority": 2},
                ],
                "completed": ["done-task"],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_list())
        assert result["count"] == 2
        assert result["total_pending"] == 2
        assert result["completed_count"] == 1
        assert len(result["tasks"]) == 2

    async def test_task_list_filters_by_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {"id": "ocd-1", "subject": "first", "kanban_status": "ready"},
                    {"id": "ocd-2", "subject": "second", "kanban_status": "backlog"},
                ],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_list(status="ready"))
        assert result["count"] == 1
        assert result["tasks"][0]["id"] == "ocd-1"

    async def test_task_list_filters_by_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {
                        "id": "ocd-1",
                        "subject": "high",
                        "kanban_status": "ready",
                        "priority": {"level": 1},
                    },
                    {
                        "id": "ocd-2",
                        "subject": "low",
                        "kanban_status": "ready",
                        "priority": {"level": 3},
                    },
                ],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_list(priority_min=2))
        assert result["count"] == 1
        assert result["tasks"][0]["id"] == "ocd-2"


class TestTaskGet:
    """Tests for ocd_task_get MCP tool."""

    async def test_task_get_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {"id": "ocd-1", "subject": "first", "description": "desc"},
                ],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_get("ocd-1"))
        assert result["id"] == "ocd-1"
        assert result["subject"] == "first"

    async def test_task_get_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {"pending": []}

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_get("ocd-99"))
        assert result["ok"] is False
        assert "not found" in result["detail"]


class TestTaskUpdate:
    """Tests for ocd_task_update MCP tool."""

    async def test_task_update_success(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "pending": [
                        {
                            "id": "ocd-1",
                            "subject": "first",
                            "kanban_status": "backlog",
                            "done": False,
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_update("ocd-1", {"kanban_status": "ready"}))
        assert result["ok"] is True
        assert "updated" in result["detail"]

        # Verify written
        updated = json.loads(tasks_path.read_text())
        assert updated["pending"][0]["kanban_status"] == "ready"

    async def test_task_update_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps({"pending": []}))

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_update("ocd-99", {"kanban_status": "ready"}))
        assert result["ok"] is False
        assert "not found" in result["detail"]

    async def test_task_update_invalid_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = json.loads(await ocd_task_update("ocd-1", {"kanban_status": "bad-status"}))
        assert result["ok"] is False
        assert "validation failed" in result["detail"]


class TestTaskLifecycleGate:
    """Tests for ocd_task_lifecycle_gate MCP tool."""

    async def test_valid_transition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {"id": "ocd-1", "subject": "first", "kanban_status": "backlog"},
                ],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_lifecycle_gate("ocd-1", "ready"))
        assert result["ok"] is True
        assert result["transition_allowed"] is True
        assert result["current_status"] == "backlog"
        assert result["target_status"] == "ready"

    async def test_invalid_transition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {
                "pending": [
                    {"id": "ocd-1", "subject": "first", "kanban_status": "done"},
                ],
            }

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_lifecycle_gate("ocd-1", "ready"))
        assert result["ok"] is False
        assert "not allowed" in result["detail"]
        assert result["allowed_transitions"] == ["archived"]

    async def test_task_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _mock_load(root):
            return {"pending": []}

        monkeypatch.setattr("ocd.mcp_server._load_tasks_json", _mock_load)
        monkeypatch.setattr("ocd.mcp_server._find_project_root", _mock_project_root)

        result = json.loads(await ocd_task_lifecycle_gate("ocd-99", "ready"))
        assert result["ok"] is False
        assert "not found" in result["detail"]


class TestTaskClaim:
    """Tests for ocd_task_claim MCP tool."""

    async def test_claim_auto_selects_highest_priority(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "meta": {"repository": "test-repo"},
                    "completed": ["ocd-0"],
                    "pending": [
                        {
                            "id": "ocd-1",
                            "subject": "low priority",
                            "priority": {"level": 3, "rpe_weight": 0.5, "value_score": 50},
                            "kanban_status": "ready",
                            "done": False,
                            "dependencies": [],
                        },
                        {
                            "id": "ocd-2",
                            "subject": "high priority",
                            "priority": {"level": 1, "rpe_weight": 0.9, "value_score": 90},
                            "kanban_status": "ready",
                            "done": False,
                            "dependencies": [],
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim())
        assert result["ok"] is True
        assert result["claimed_task"]["id"] == "ocd-2"

        # Verify written
        updated = json.loads(tasks_path.read_text())
        claimed = next(t for t in updated["pending"] if t["id"] == "ocd-2")
        assert claimed["kanban_status"] == "in_progress"

    async def test_claim_specific_task(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "meta": {"repository": "test-repo"},
                    "completed": [],
                    "pending": [
                        {
                            "id": "ocd-1",
                            "subject": "first",
                            "kanban_status": "ready",
                            "priority": {"level": 2},
                            "done": False,
                            "dependencies": [],
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim(task_id="ocd-1"))
        assert result["ok"] is True
        assert result["claimed_task"]["id"] == "ocd-1"
        assert "bus_message" in result

    async def test_claim_skips_done_tasks(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "meta": {"repository": "test-repo"},
                    "completed": [],
                    "pending": [
                        {
                            "id": "ocd-1",
                            "subject": "done task",
                            "kanban_status": "backlog",
                            "priority": {"level": 1},
                            "done": True,
                            "dependencies": [],
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim())
        assert result["ok"] is False
        assert "no claimable tasks" in result["detail"]

    async def test_claim_skips_blocked_by_deps(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "meta": {"repository": "test-repo"},
                    "completed": [],
                    "pending": [
                        {
                            "id": "ocd-2",
                            "subject": "blocked task",
                            "kanban_status": "ready",
                            "priority": {"level": 1},
                            "done": False,
                            "dependencies": ["ocd-1"],
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim())
        assert result["ok"] is False
        assert "no claimable tasks" in result["detail"]

    async def test_claim_task_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(json.dumps({"meta": {"repository": "test"}, "pending": []}))

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim(task_id="ocd-99"))
        assert result["ok"] is False

    async def test_claim_bus_message_format(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        tasks_path = tmp_path / "tasks.json"
        tasks_path.write_text(
            json.dumps(
                {
                    "meta": {"repository": "test-repo"},
                    "completed": [],
                    "pending": [
                        {
                            "id": "ocd-1",
                            "subject": "first",
                            "kanban_status": "ready",
                            "priority": {"level": 2},
                            "done": False,
                            "dependencies": [],
                        },
                    ],
                }
            )
        )

        monkeypatch.setattr("ocd.mcp_server._find_project_root", lambda: tmp_path)

        result = json.loads(await ocd_task_claim())
        assert result["ok"] is True
        msg = result["bus_message"]
        assert msg["type"] == "status"
        assert msg["topic"] == "agent-claim"
        assert msg["payload"]["task"] == "ocd-1"
        assert msg["payload"]["repo"] == "test-repo"
