# O.C.D. — Obsessive Compulsive Driver

> **Obsessive Compulsive Driver** (OCD) is the discipline & enforcement layer for MCP-based
> agents.
>
> It externalizes obsessive attention to detail into a quality enforcement system that catches
> violations before they reach production.

## The OCD Parallel

OCD isn't just anxiety-driven repetition — it's a hyper-tuned sensitivity to deviation. The OC
brain notices the crooked picture frame, the slightly misaligned tile, the inconsistency that
everyone else filters out as "good enough."

That sensitivity is exhausting in daily life. But in software? It's exactly what you want at the
quality gate:

- **Intolerance of inconsistency**: A variable named `userId` in one file and `user_id` in
  another? The OC brain flags it instantly — just like `ocd_check` catches style drift before it
  becomes technical debt.
- **Ritualistic verification**: Before leaving the house: stove off, door locked, lights out.
  Before pushing code: branch protection, standards hash, secret scan, ruff check. Same loop,
  different checklist.
- **Perfectionism as a service**: The OC brain rewrites a sentence seven times until it's right.
  OCD reruns formatters and linters until the codebase is uniformly clean — not because seven
  passes are needed, but because zero tolerance for mess is the standard.
- **Resistance to entropy**: Without active maintenance, codebases drift. The OC brain fights
  entropy with constant checking. OCD embeds that vigilance into the pipeline so agents don't have
  to remember every rule — the system enforces it for them.

This package externalizes that hypervigilance into tooling:

- Checking the same things, the same way, every time — without fatigue
- Never letting "good enough" become the standard
- Noticing what's out of place before it causes a problem
- Refusing to ship until every gate is green

## What This Is

An MCP-native quality enforcement server. OCD provides a single `ocd-mcp` FastMCP stdio server
that runs quality gates, verifies standards, scans for secrets, formats and lints code, and
enforces the Nine Standards — all through typed MCP tools. There is no CLI, no importable library,
and no hard dependency on any other BrainXio package.

## Core Architecture

### Modes

OCD operates in modes. Each mode activates a specific bundle of rules, skills, and gates:

- **developer** — standard development gates: branch protection, standards verification,
  secret scanning, linting, formatting. All checks at `strict` or `warn` level.
- **research** — exploratory work gates: dead code and surface area checks skip. Relaxed
  enforcement for prototyping and investigation.
- **review** — PR review gates: all nine standards at `strict`. Maximal enforcement for
  audit and pre-merge review.
- **ops** — operational gates: defense in depth and consistent defaults are paramount.
  Surface area and honesty checks at `warn` level.
- **personal** — personal project gates: developer-like defaults, user-configurable.

### MCP Server

The sole interface is `ocd-mcp`, a FastMCP stdio server registered via `.mcp.json`.

| Tool                            | Purpose                                          | OCD Parallel                                          |
| ------------------------------- | ------------------------------------------------ | ----------------------------------------------------- |
| `ocd_check`                     | Fast local quality gate                          | The quick pre-leaving-the-house check                 |
| `ocd_ci_check`                  | Full CI mirror of all quality gates              | The exhaustive inspection before guests arrive        |
| `ocd_get_mode`                  | Return currently active mode                     | Checking which checklist you're on                    |
| `ocd_get_rules`                 | Return structured enforcement rules              | Reading the manual cover to cover                     |
| `ocd_lint_work`                 | Lint specified files                             | Counting the steps as you walk                        |
| `ocd_run_formatters`            | Run formatters with auto-fix                     | Aligning everything at perfect right angles           |
| `ocd_scan_secrets`              | Scan for secrets using gitleaks                  | Checking the stove is off (again)                     |
| `ocd_set_mode`                  | Switch active rule/gate/skill set                | Switching between different ritual routines           |
| `ocd_standard_check`            | Run a single Nine Standards check                | Verifying one item on the checklist                   |
| `ocd_standard_check_all`        | Run all Nine Standards checks                    | The full Sunday cleaning routine                      |
| `ocd_standard_list`             | List available standard check names              | Reading the table of contents aloud                   |
| `ocd_standards_update`          | Report current standards reference               | Updating the mental checklist                         |
| `ocd_standards_verify`          | Verify standards hash consistency                | Making sure the rules haven't changed since yesterday |
| `ocd_task_get`                  | Get a single task by ID                          | Reading the sticky note very carefully                |
| `ocd_task_lifecycle_gate`       | Check task transition validity                   | Making sure you're not skipping steps                 |
| `ocd_task_list`                 | List tasks with status/priority filters          | Scanning the to-do board for what's next              |
| `ocd_task_update`               | Update task fields with validation               | Correcting a mistake on the checklist                 |
| `ocd_validate_mcp_conventions`  | Validate MCP tool naming conventions             | Checking every drawer is labeled correctly            |
| `ocd_validate_ppac_consistency` | Validate PPAC loop consistency                   | Tracing the circuit to make sure it loops             |
| `ocd_verify_commit`             | Check commit messages for prohibited attribution | Re-reading the email one more time before sending     |

## Nine Standards

For detailed documentation of all Nine Standards with code examples, see [`docs/standards.md`](docs/standards.md).

## Installation

OCD is distributed as a Python package. The `.mcp.json` in the repo root auto-starts the MCP
server when Claude Code opens the project.

```bash
# Clone the repo
git clone git@github.com:BrainXio/obsessive-compulsive-driver.git

# Install the package
uv pip install -e .
```

## Usage

### Run a pre-commit quality gate

```
ocd_check
```

Runs branch protection verification, standards hash check, staged secret scan, and ruff lint.
Returns a pass/fail summary with per-check details. Target: under 10 seconds.

### Run the full CI mirror before pushing

```
ocd_ci_check(fast=false)
```

Adds mypy, yamllint, pytest, and ruff format checking on top of the standard gate. Set `fast=true`
to run a diff-aware test subset instead of the full suite.

### Verify a commit message

```
ocd_verify_commit(message="feat: add token refresh with Claude")
```

Checks the message against prohibited attribution patterns. Returns the specific violations if any
are found.

### Switch the active mode

```
ocd_set_mode(mode="developer")
```

Activates a specific rule/gate/skill bundle. Phase 1 supports `developer` mode only.

## Runtime State Location

### Environment Variables

| Variable   | Purpose                                        |
| ---------- | ---------------------------------------------- |
| `OCD_MODE` | Default mode at startup (default: `developer`) |

### Cross-Repo Enforcement

Set `OCD_MODE=review` when running in a PR review context to activate diff-aware checks:

```bash
OCD_MODE=review uv run ocd-mcp
```

## Design Philosophy

**Enforcement over trust.** Agents forget rules. Prompts drift. Hooks get skipped. The only thing
that works reliably is automated gates that run every time.

**Explicit over implicit.** The Nine Standards are embedded as hash-verified constants. You can't
accidentally change the rules — the hash will tell you they changed.

**Graceful degradation.** Missing gitleaks? Secrets check skips. No mypy? Type check skips. Every
tool degrades to `"skipped"` instead of crashing — you get the checks you can, with clear
messaging about what's missing.
