# OCD Architecture

## Role

OCD is the **discipline & enforcement layer** in the BrainXio ecosystem. It turns
obsessive attention to detail, perfectionism, and ritualistic discipline into an
external quality enforcement system that forces agents to stay aligned with the
Nine Standards at all times.

## Boundaries

- **OCD** drives enforcement (rules, gates, standards)
- **ADHD** handles coordination (message bus, agent lifecycle)
- **ASD** manages memory (knowledge compilation, semantic storage)

OCD never imports or hard-depends on ADHD or ASD. Communication happens
exclusively through the MCP registry when the three servers run together.

## Package Structure

```
src/ocd/
├── __init__.py              # Package marker with version
├── mcp_server.py            # FastMCP server with all 20 tool definitions
├── rules.py                 # Structured protocol rules (get_rules pattern)
├── standards_data.py        # Embedded Nine Standards, hash logic, AI patterns
├── modes/
│   └── mode_definitions.py  # All 5 mode definitions with per-standard levels
└── task_enforcer/
    ├── __init__.py          # Task-enforcer module exports
    ├── cross_repo.py        # Cross-repo dependency resolution
    ├── lifecycle.py         # Task lifecycle transition gates
    ├── pruning.py           # Stale task detection and pruning
    ├── rpe_bridge.py        # RPE telemetry bridge to Another-Intelligence
    ├── schema.py            # Pydantic task schema models
    └── validation.py        # Task validation and cross-repo checks
```

## MCP Tools

All functionality is exposed as typed MCP tools via FastMCP stdio transport.
There is no CLI, no standalone scripts, and no Agent SDK orchestration.

### Mode Management

| Tool            | Signature            | Purpose                               |
| --------------- | -------------------- | ------------------------------------- |
| `ocd_get_mode`  | `() -> str`          | Return the currently active mode      |
| `ocd_get_rules` | `() -> str`          | Return structured protocol rules      |
| `ocd_set_mode`  | `(mode: str) -> str` | Switch the active rule/gate/skill set |

### Quality Gates

| Tool           | Signature                     | Purpose                              |
| -------------- | ----------------------------- | ------------------------------------ |
| `ocd_check`    | `() -> str`                   | Fast local quality gate (pre-commit) |
| `ocd_ci_check` | `(fast: bool = False) -> str` | Full CI mirror of all quality gates  |

### Standards Checks

| Tool                     | Signature            | Purpose                                   |
| ------------------------ | -------------------- | ----------------------------------------- |
| `ocd_standard_check`     | `(name: str) -> str` | Run a single named standard check         |
| `ocd_standard_check_all` | `() -> str`          | Run all Nine Standards checks             |
| `ocd_standard_list`      | `() -> str`          | List available standard check names       |
| `ocd_standards_update`   | `() -> str`          | Report current standards reference + hash |
| `ocd_standards_verify`   | `() -> str`          | Verify standards hash consistency         |

### Validators

| Tool                            | Signature   | Purpose                              |
| ------------------------------- | ----------- | ------------------------------------ |
| `ocd_validate_mcp_conventions`  | `() -> str` | Validate MCP tool naming conventions |
| `ocd_validate_ppac_consistency` | `() -> str` | Validate PPAC loop consistency       |

### Enforcement

| Tool                 | Signature                       | Purpose                                       |
| -------------------- | ------------------------------- | --------------------------------------------- |
| `ocd_lint_work`      | `(files: list[str]) -> str`     | Lint specified files and report violations    |
| `ocd_run_formatters` | `() -> str`                     | Run formatters with auto-fix                  |
| `ocd_scan_secrets`   | `(staged: bool = False) -> str` | Scan for secrets using gitleaks               |
| `ocd_verify_commit`  | `(message: str) -> str`         | Check commit messages for prohibited patterns |

### Task Enforcer

| Tool                      | Signature                                            | Purpose                                  |
| ------------------------- | ---------------------------------------------------- | ---------------------------------------- |
| `ocd_task_get`            | `(task_id: str) -> str`                              | Get a task by ID                         |
| `ocd_task_lifecycle_gate` | `(task_id: str, target_status: str) -> str`          | Run lifecycle gate checks on transitions |
| `ocd_task_list`           | `(status: str = None, priority_min: int = 0) -> str` | List all tracked tasks with filters      |
| `ocd_task_update`         | `(task_id: str, updates: dict) -> str`               | Update task status and metadata          |

## Mode System

OCD operates in five modes. Each mode activates a specific bundle of rules and
enforcement levels. All Five Standards use three levels: `strict`, `warn`, and
`skip`.

| Mode        | Purpose                                      | Key Relaxations              |
| ----------- | -------------------------------------------- | ---------------------------- |
| `developer` | Baseline development — strict core gates     | Surface area, SST at warn    |
| `research`  | Exploration/prototyping — relaxed dead code  | Dead code, surface area skip |
| `review`    | Pre-merge audit — all nine standards strict  | None                         |
| `ops`       | Operations/security — defense-in-depth focus | Surface area at warn         |
| `personal`  | User-configurable — developer-like defaults  | Several standards at warn    |

Mode definitions live in `src/ocd/modes/mode_definitions.py` as
`MODE_DEFINITIONS` with per-standard enforcement levels. The mode switch via
`ocd_set_mode` persists for the lifetime of the MCP server session.

## Task Enforcer

The task-enforcer module provides structured task lifecycle management through
MCP tools. Tasks follow a Kanban flow:

```
backlog → ready → in_progress → done → archived
                 ↘ blocked ↗
```

Each transition triggers appropriate Nine Standards checks:

| Transition              | Gates Required                     |
| ----------------------- | ---------------------------------- |
| `backlog` → `ready`     | Deterministic Ordering, Minimal SA |
| `ready` → `in_progress` | No Dead Code, Single Source        |
| `in_progress` → `done`  | All Nine Standards                 |
| any → `blocked`         | Reason recording only              |

Cross-repo dependencies are validated by resolving task IDs across all four
BrainXio repos (ADHD, AI, ASD, OCD) and detecting circular or unresolvable
references.

## Graceful Degradation

All tools gracefully handle missing external dependencies (gitleaks, mypy,
yamllint, shellcheck). Tools return a `"skipped"` status when a required
binary is not installed. If the MCP server itself is unreachable, callers
log a warning and continue without enforcement rather than halting.

## The Nine Standards

The Nine Standards are embedded as Python constants in `standards_data.py`.
They are the immutable quality baseline:

1. No Dead Code
2. Single Source of Truth
3. Consistent Defaults
4. Minimal Surface Area
5. Defense in Depth
6. Structural Honesty
7. Progressive Simplification
8. Deterministic Ordering
9. Inconsistent Elimination

Detailed documentation with examples is in [../reference/standards.md](../reference/standards.md).
