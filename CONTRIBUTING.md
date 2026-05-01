# Contributing to O.C.D.

## Branch Naming

Use conventional prefix and a short kebab-case description:

| Prefix | When to use |
| ---------- | ---------------------------------------- |
| `feat/` | New feature or enhancement |
| `fix/` | Bug fix |
| `docs/` | Documentation changes only |
| `chore/` | Maintenance, tooling, CI, dependencies |
| `refactor/`| Code restructuring without feature change|
| `test/` | Test additions or improvements |

Examples: `feat/mcp-convention-validator`, `fix/false-positive-dead-code`, `docs/standards-guide`.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`.

Scopes: `gate`, `ci`, `lint`, `secrets`, `mode`, `standards`, `mcp`, `docs`.

Examples:

- `feat(gate): add MCP convention validation check`
- `fix(standards): handle pytest discovery in dead code checker`
- `docs(mode): add ops mode documentation`

Keep descriptions concise and imperative.

## PR Workflow

1. Create a feature branch from `main`

2. Implement with tests

3. Run the local CI gate before pushing:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest -q
   uv run mdformat --check README.md docs/
   ```

4. Push and open a PR against `main`

5. Post the PR URL to the ADHD bus for review

6. Do not self-merge — wait for a supporter review

## Code Style

- Type hints on all public functions and classes
- Line length: 100 characters
- Use Pydantic for configuration and data models
- Tests use `pytest` (not `unittest`)
- Imports sorted via `ruff` (enforced in CI)
- No attribution of any kind in commits, PRs, comments, or docs

## Nine Standards

When modifying standards checkers:

- Run `ocd_standard_check_all` after any change to verify all nine standards pass
- The standards hash must remain consistent — run `ocd_standards_update` if intentional
- False positives should be handled by improving the checker, not by adding skip lists
- New modes require updating `docs/architecture.md` and the mode table in README.md

## Getting Help

Post questions to the ADHD bus with `type: question` and `topic: ocd`. For standard violation questions, run `ocd_standard_check_all` and include results.
