"""Self-describing rules for the OCD discipline and enforcement layer.

Exposes the Nine Standards, mode definitions, enforcement pipeline, and
environment variable reference so agents can discover OCD capabilities
at runtime via ocd_get_rules.
"""

from __future__ import annotations

from ocd.modes.mode_definitions import MODE_DEFINITIONS
from ocd.standards_data import NINE_STANDARDS_SUMMARY, NINE_STANDARDS_VERSION


def get_rules() -> dict[str, object]:
    """Return structured rules for the OCD enforcement layer.

    Versioned and matching the current enforcement model. MCP clients can
    call ocd_get_rules at startup to learn the quality gate protocol.
    """
    modes_list: list[dict[str, object]] = []
    for name, config in MODE_DEFINITIONS.items():
        modes_list.append(
            {
                "name": name,
                "description": config["description"],
                "standards": {s: level for s, level in config["standards"].items()},
            }
        )

    return {
        "package": "ocd",
        "version": NINE_STANDARDS_VERSION,
        "description": "Discipline and enforcement layer — rules, gates, modes, task-enforcer",
        "nine_standards": {
            "version": NINE_STANDARDS_VERSION,
            "summary": NINE_STANDARDS_SUMMARY.strip(),
            "checks": [
                {
                    "name": "no-dead-code",
                    "tool": "ocd_standard_check",
                    "param": "no-dead-code",
                },
                {
                    "name": "single-source-of-truth",
                    "tool": "ocd_standard_check",
                    "param": "single-source-of-truth",
                },
                {
                    "name": "consistent-defaults",
                    "tool": "ocd_standard_check",
                    "param": "consistent-defaults",
                },
                {
                    "name": "minimal-surface-area",
                    "tool": "ocd_standard_check",
                    "param": "minimal-surface-area",
                },
                {
                    "name": "defense-in-depth",
                    "tool": "ocd_standard_check",
                    "param": "defense-in-depth",
                },
                {
                    "name": "structural-honesty",
                    "tool": "ocd_standard_check",
                    "param": "structural-honesty",
                },
                {
                    "name": "progressive-simplification",
                    "tool": "ocd_standard_check",
                    "param": "progressive-simplification",
                },
                {
                    "name": "deterministic-ordering",
                    "tool": "ocd_standard_check",
                    "param": "deterministic-ordering",
                },
                {
                    "name": "inconsistent-elimination",
                    "tool": "ocd_standard_check",
                    "param": "inconsistent-elimination",
                },
            ],
        },
        "modes": modes_list,
        "quality_gates": {
            "fast_gate": {
                "description": "Quick local quality check (<10s)",
                "tool": "ocd_check",
                "checks": [
                    "branch-protection",
                    "standards-verify",
                    "secret-scan-staged",
                    "ruff-check",
                ],
            },
            "full_ci": {
                "description": "Full CI mirror running all quality gates",
                "tool": "ocd_ci_check",
                "fast_variant": "ocd_ci_check(fast=True) — skips full test suite",
                "checks": [
                    "standards-verify",
                    "secret-scan-full",
                    "ruff-check",
                    "ruff-format-check",
                    "mypy-strict",
                    "yamllint",
                    "pytest",
                ],
            },
        },
        "lifecycle_gates": {
            "description": "Per-transition standard checks for task kanban status changes",
            "tool": "ocd_task_lifecycle_gate",
            "transitions": {
                "backlog_to_ready": ["deterministic-ordering", "minimal-surface-area"],
                "ready_to_in_progress": ["no-dead-code", "single-source-of-truth"],
                "in_progress_to_done": ["all nine standards"],
            },
        },
        "env_vars": [
            {
                "name": "OCD_MODE",
                "purpose": "Active enforcement mode",
                "valid_values": sorted(MODE_DEFINITIONS.keys()),
                "default": "developer",
            },
        ],
        "tools": [
            {"tool": "ocd_set_mode", "purpose": "Switch active enforcement mode"},
            {"tool": "ocd_get_mode", "purpose": "Get current active mode"},
            {"tool": "ocd_check", "purpose": "Run fast local quality gate"},
            {"tool": "ocd_ci_check", "purpose": "Run full local CI mirror"},
            {"tool": "ocd_verify_commit", "purpose": "Verify commit for prohibited attribution"},
            {"tool": "ocd_scan_secrets", "purpose": "Scan for secrets using gitleaks"},
            {"tool": "ocd_run_formatters", "purpose": "Run ruff format + fix"},
            {"tool": "ocd_lint_work", "purpose": "Lint specified files"},
            {"tool": "ocd_standards_verify", "purpose": "Verify standards hash integrity"},
            {"tool": "ocd_standards_update", "purpose": "Recompute standards hash"},
            {"tool": "ocd_standard_check", "purpose": "Run a single Nine Standards check"},
            {"tool": "ocd_standard_check_all", "purpose": "Run all Nine Standards checks"},
            {"tool": "ocd_standard_list", "purpose": "List available standard check names"},
            {"tool": "ocd_validate_mcp_conventions", "purpose": "Validate MCP naming conventions"},
            {"tool": "ocd_validate_ppac_consistency", "purpose": "Validate PPAC loop consistency"},
            {"tool": "ocd_task_list", "purpose": "List tasks with status/priority filters"},
            {"tool": "ocd_task_get", "purpose": "Get single task by ID with full details"},
            {"tool": "ocd_task_update", "purpose": "Update task fields with validation"},
            {"tool": "ocd_task_lifecycle_gate", "purpose": "Check task transition validity"},
            {"tool": "ocd_get_rules", "purpose": "Return these enforcement rules"},
        ],
    }
