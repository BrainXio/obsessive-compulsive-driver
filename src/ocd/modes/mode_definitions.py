"""OCD mode definitions.

Each mode is a dict with:
- name: str
- description: str
- standards: dict[str, str] — standard_name → enforcement level (strict/warn/skip)
"""

from __future__ import annotations

MODE_DEFINITIONS: dict[str, dict] = {
    "developer": {
        "description": "Baseline development mode — all standards enforced at strict level",
        "standards": {
            "no-dead-code": "strict",
            "single-source-of-truth": "warn",
            "consistent-defaults": "strict",
            "minimal-surface-area": "warn",
            "defense-in-depth": "strict",
            "structural-honesty": "warn",
            "progressive-simplification": "warn",
            "deterministic-ordering": "strict",
            "inconsistent-elimination": "strict",
        },
    },
    "research": {
        "description": (
            "Relaxed mode for exploration/prototyping — dead code and surface area checks skip"
        ),
        "standards": {
            "no-dead-code": "skip",
            "single-source-of-truth": "warn",
            "consistent-defaults": "warn",
            "minimal-surface-area": "skip",
            "defense-in-depth": "skip",
            "structural-honesty": "warn",
            "progressive-simplification": "skip",
            "deterministic-ordering": "warn",
            "inconsistent-elimination": "warn",
        },
    },
    "review": {
        "description": (
            "Review/audit mode — structural honesty and ordering are strict, broader surface checks"
        ),
        "standards": {
            "no-dead-code": "strict",
            "single-source-of-truth": "strict",
            "consistent-defaults": "strict",
            "minimal-surface-area": "strict",
            "defense-in-depth": "strict",
            "structural-honesty": "strict",
            "progressive-simplification": "strict",
            "deterministic-ordering": "strict",
            "inconsistent-elimination": "strict",
        },
    },
    "ops": {
        "description": (
            "Operations/security mode — defense in depth and consistent defaults are paramount"
        ),
        "standards": {
            "no-dead-code": "strict",
            "single-source-of-truth": "strict",
            "consistent-defaults": "strict",
            "minimal-surface-area": "warn",
            "defense-in-depth": "strict",
            "structural-honesty": "warn",
            "progressive-simplification": "warn",
            "deterministic-ordering": "strict",
            "inconsistent-elimination": "strict",
        },
    },
    "personal": {
        "description": (
            "User-configurable personal mode — "
            "defaults to developer levels, adjustable per preference"
        ),
        "standards": {
            "no-dead-code": "strict",
            "single-source-of-truth": "warn",
            "consistent-defaults": "strict",
            "minimal-surface-area": "warn",
            "defense-in-depth": "warn",
            "structural-honesty": "warn",
            "progressive-simplification": "warn",
            "deterministic-ordering": "strict",
            "inconsistent-elimination": "strict",
        },
    },
}

ALLOWED_MODES: frozenset[str] = frozenset(MODE_DEFINITIONS.keys())


def get_mode_config(mode: str) -> dict:
    """Return the full mode configuration dict."""
    return MODE_DEFINITIONS.get(mode, MODE_DEFINITIONS["developer"])


def get_standard_level(mode: str, standard: str) -> str:
    """Return enforcement level for a standard in the given mode.

    Returns 'strict' if mode or standard is unknown (safe default).
    """
    mode_config = MODE_DEFINITIONS.get(mode, MODE_DEFINITIONS["developer"])
    return mode_config["standards"].get(standard, "strict")
