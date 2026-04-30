#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# OCD Pre-Commit Hook
# ===================
# Runs OCD quality gates on staged changes before allowing a commit.
# Install: cp scripts/pre-commit-ocd.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#
# Requires: ruff, Python 3.12+ (gitleaks optional)
#
# Fails commit on:
#   - Commits directly to 'main' branch
#   - Secrets in staged changes
#   - Ruff lint violations
#   - Ruff format violations
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

exit_code=0
issues=()

# Find project root (nearest parent with .git/)
project_root="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
cd "$project_root"

# ── Check 1: Branch protection ──────────────────────────────────────────────────

branch="$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")"
if [ "$branch" = "main" ]; then
    echo -e "${RED}[FAIL]${NC} branch-protection: commits on 'main' are prohibited"
    exit_code=1
    issues+=("branch-protection: direct commit to main")
else
    echo -e "${GREEN}[PASS]${NC} branch-protection: $branch"
fi

# ── Check 2: Secret scan (staged only) ──────────────────────────────────────────

if command -v gitleaks &>/dev/null; then
    gitleaks_config="$project_root/.gitleaks.toml"
    config_args=()
    [ -f "$gitleaks_config" ] && config_args=(-c "$gitleaks_config")

    if gitleaks protect --staged "${config_args[@]}" --log-level error 2>/dev/null; then
        echo -e "${GREEN}[PASS]${NC} secret-scan: no secrets detected"
    else
        echo -e "${RED}[FAIL]${NC} secret-scan: potential secrets in staged changes"
        exit_code=1
        issues+=("secret-scan: secrets detected in staged changes")
    fi
else
    echo -e "${YELLOW}[SKIP]${NC} secret-scan: gitleaks not installed"
fi

# ── Check 3: Ruff lint ───────────────────────────────────────────────────────────

if command -v ruff &>/dev/null; then
    if ruff check src/ tests/ 2>/dev/null; then
        echo -e "${GREEN}[PASS]${NC} ruff-check: clean"
    else
        echo -e "${RED}[FAIL]${NC} ruff-check: lint violations found"
        exit_code=1
        issues+=("ruff-check: lint violations")
    fi
else
    echo -e "${YELLOW}[SKIP]${NC} ruff-check: ruff not installed"
fi

# ── Check 4: Ruff format ────────────────────────────────────────────────────────

if command -v ruff &>/dev/null; then
    if ruff format --check src/ tests/ 2>/dev/null; then
        echo -e "${GREEN}[PASS]${NC} ruff-format: clean"
    else
        echo -e "${RED}[FAIL]${NC} ruff-format: files would be reformatted"
        exit_code=1
        issues+=("ruff-format: unformatted files")
    fi
else
    echo -e "${YELLOW}[SKIP]${NC} ruff-format: ruff not installed"
fi

# ── Summary ─────────────────────────────────────────────────────────────────────

echo ""
if [ "$exit_code" -eq 0 ]; then
    echo -e "${GREEN}OCD gate: all checks passed${NC}"
else
    echo -e "${RED}OCD gate: ${#issues[@]} check(s) failed:${NC}"
    for issue in "${issues[@]}"; do
        echo -e "  ${RED}→${NC} $issue"
    done
    echo ""
    echo "Fix the issues above and try again."
    echo "To bypass (emergency only): git commit --no-verify"
fi

exit "$exit_code"
