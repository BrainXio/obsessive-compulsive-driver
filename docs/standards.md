# The Nine Standards

OCD enforces nine quality standards. Each has a name, a rule, an automated check,
and concrete examples of violations and fixes.

______________________________________________________________________

## 1. No Dead Code

**Rule:** Every line must be reachable, used, and necessary.

### Python

| Before                         | After                                     |
| ------------------------------ | ----------------------------------------- |
| `UNUSED = "never read"`        | (deleted)                                 |
| `def old_path(): return "/v1"` | (deleted if no callers)                   |
| `if False: activate_legacy()`  | `activate_legacy()` (or delete the block) |

### Markdown / Config

| Before                                           | After                  |
| ------------------------------------------------ | ---------------------- |
| `# TODO: remove this section` (stale since 2024) | (deleted or addressed) |
| `legacy_endpoint = "/v0"` (no consumers)         | (deleted)              |

**Check:** `ocd_standard_check("no-dead-code")` — AST-based scan for defined-but-unreferenced names.

______________________________________________________________________

## 2. Single Source of Truth

**Rule:** Every fact lives in exactly one place. Reference it; don't repeat it.

### Python

| Before                                      | After                                                    |
| ------------------------------------------- | -------------------------------------------------------- |
| `VERSION = "2.0"` in `a.py`, `b.py`, `c.py` | `VERSION = "2.0"` in `constants.py`, imported everywhere |
| `DEFAULT_HOST = "localhost"` in 5 files     | One config module, imported                              |

### JSON Config

| Before                                          | After                         |
| ----------------------------------------------- | ----------------------------- |
| `"port": 8080` in `.mcp.json` and `config.yaml` | One source, referenced by key |

**Check:** `ocd_standard_check("single-source-of-truth")` — flags strings >= 20 chars appearing in 3+ files.

______________________________________________________________________

## 3. Consistent Defaults

**Rule:** Every configuration value has exactly one default, stated in one place.

### Python

| Before                                                    | After                                                 |
| --------------------------------------------------------- | ----------------------------------------------------- |
| `os.getenv("TIMEOUT", "30")` and `config["timeout"] = 60` | Single default in one location with explicit override |
| `debug = False` in two modules                            | Extract to shared config                              |

### TOML

| Before                                                                            | After                                |
| --------------------------------------------------------------------------------- | ------------------------------------ |
| `[tool.ruff]` with `line-length = 100` and `[tool.black]` with `line-length = 88` | Align on one value, delete the other |

**Check:** `ocd_standard_check("consistent-defaults")` — scans config files for key conflicts.

______________________________________________________________________

## 4. Minimal Surface Area

**Rule:** Every knob, flag, and conditional branch is a maintenance burden.

### Python

| Before                                             | After                                               |
| -------------------------------------------------- | --------------------------------------------------- |
| 15 boolean feature flags, 12 defaulting to `False` | Remove unused flags; merge related ones into a list |
| 40-line if/elif/else chain                         | Replace with lookup table or dict dispatch          |

### TOML / YAML

| Before                                                                       | After                                              |
| ---------------------------------------------------------------------------- | -------------------------------------------------- |
| `enable_feature_a = false` (never enabled in any env)                        | (deleted)                                          |
| 3 separate flags for `retry_on_timeout`, `retry_on_connect`, `retry_on_read` | One `retry_policy: ["timeout", "connect", "read"]` |

**Check:** `ocd_standard_check("minimal-surface-area")` — flags files with >= 10 boolean flags or >= 30 branches.

______________________________________________________________________

## 5. Defense in Depth

**Rule:** Security is layered. Every trust boundary gets its own validation.

### Python

| Before                             | After                                                         |
| ---------------------------------- | ------------------------------------------------------------- |
| Input validated only at HTTP layer | Validate at HTTP layer + service layer + database constraints |
| Secret scanning only in CI         | Pre-commit hooks + CI + periodic full scan                    |

### Config

| Before                 | After                                              |
| ---------------------- | -------------------------------------------------- |
| No `.gitleaks.toml`    | `.gitleaks.toml` with project-specific rules       |
| No security lint rules | Ruff rules including `S` (security) checks         |
| No pre-commit hooks    | `.pre-commit-config.yaml` with secret + lint gates |

**Check:** `ocd_standard_check("defense-in-depth")` — verifies presence of gitleaks, security lint rules, and pre-commit hooks.

______________________________________________________________________

## 6. Structural Honesty

**Rule:** Code should say what it does and do what it says.

### Python

| Before                                                         | After                                                           |
| -------------------------------------------------------------- | --------------------------------------------------------------- |
| `def apply_rules():` → also fetches remote data                | Rename to `fetch_and_apply_rules()` or split into two functions |
| `def ready():` → `return True` (returns bool, no `is_` prefix) | `def is_ready():` → `return True`                               |
| `def apply_patch():` → returns `None` (silent failure)         | Return a result object or raise on failure                      |

### Markdown / Comments

| Before                                           | After                                              |
| ------------------------------------------------ | -------------------------------------------------- |
| `# Always blocks telemetry` above gated code     | Code matches comment — no gate, or comment updated |
| `ALLOWED_DOMAINS` contains `""` as a placeholder | Empty list `[]` or properly populated              |

**Check:** `ocd_standard_check("structural-honesty")` — flags bool-returning functions without `is_`/`has_`/`check_` prefix, and action functions returning None.

______________________________________________________________________

## 7. Progressive Simplification

**Rule:** After every feature, ask: can this be shorter without losing meaning?

### Python

| Before                                                                                      | After                                |
| ------------------------------------------------------------------------------------------- | ------------------------------------ |
| 450-line module with 12 functions                                                           | Split into 2-3 focused modules       |
| `python<br>if x == "a": return 1<br>elif x == "b": return 2<br>elif x == "c": return 3<br>` | `return {"a": 1, "b": 2, "c": 3}[x]` |

### Markdown

| Before                                                   | After                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------------------------ |
| 300-line README with installation, usage, FAQ, changelog | Split: README (quickstart), docs/install.md, docs/usage.md, CHANGELOG.md |

**Check:** `ocd_standard_check("progressive-simplification")` — flags Python files > 300 lines and markdown files > 200 lines.

______________________________________________________________________

## 8. Deterministic Ordering

**Rule:** When no logical sequence is required, sort alphabetically.

### Python

| Before                                    | After                                     |
| ----------------------------------------- | ----------------------------------------- |
| `__all__ = ["MCPClient", "Auth", "Base"]` | `__all__ = ["Auth", "Base", "MCPClient"]` |
| Imports: `from x import c, a, b`          | `from x import a, b, c`                   |

### Markdown

| Before                        | After                             |
| ----------------------------- | --------------------------------- |
| Table rows in insertion order | Table rows sorted by first column |
| Bullet list in random order   | Bullet list alphabetically sorted |

### JSON / TOML

| Before                                      | After                                       |
| ------------------------------------------- | ------------------------------------------- |
| `dependencies = ["pytest", "ruff", "mypy"]` | `dependencies = ["mypy", "pytest", "ruff"]` |

**Check:** `ocd_standard_check("deterministic-ordering")` — checks markdown tables, bullet lists, and dependency lists for alphabetical ordering.

______________________________________________________________________

## 9. Inconsistent Elimination

**Rule:** When two sources disagree, resolve the conflict. Pick the canonical source and align everything to it.

### Python / Config

| Before                                                               | After                                                             |
| -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Ruff says single quotes; committed files use double quotes           | Align all files to the formatter (or update the formatter config) |
| `pyproject.toml` says `line-length = 100`; files have 120-char lines | Reformat to 100 chars                                             |
| Docs say "returns a dict"; code returns a Pydantic model             | Align docs or code                                                |

### Markdown

| Before                                      | After                          |
| ------------------------------------------- | ------------------------------ |
| `mdformat` wants `-` bullets; files use `*` | Run `mdformat` or configure it |
| Architecture doc says 3 modules; code has 5 | Update the doc                 |

**Check:** `ocd_standard_check("inconsistent-elimination")` — runs `ruff format --check` and flags mismatches.

______________________________________________________________________

## Using Via MCP

```python
# Run a single standard check
ocd_standard_check("no-dead-code")

# Run all nine
ocd_standard_check_all()

# List available standards
ocd_standard_list()
```

Each check returns:

```json
{
  "standard": "No Dead Code",
  "status": "pass",
  "evidence": []
}
```

## Mode-Specific Enforcement

Different modes enforce standards at different levels:

| Standard                   | developer | research | review | ops    | personal |
| -------------------------- | --------- | -------- | ------ | ------ | -------- |
| Consistent Defaults        | strict    | warn     | strict | strict | strict   |
| Defense in Depth           | strict    | skip     | strict | strict | warn     |
| Deterministic Ordering     | strict    | warn     | strict | strict | strict   |
| Inconsistent Elimination   | strict    | warn     | strict | strict | strict   |
| Minimal Surface Area       | warn      | skip     | strict | warn   | warn     |
| No Dead Code               | strict    | skip     | strict | strict | strict   |
| Progressive Simplification | warn      | skip     | strict | warn   | warn     |
| Single Source of Truth     | warn      | warn     | strict | strict | warn     |
| Structural Honesty         | warn      | warn     | strict | warn   | warn     |

Switch modes with `ocd_set_mode("review")` for full enforcement or
`ocd_set_mode("research")` for exploratory work.
