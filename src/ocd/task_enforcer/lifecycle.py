"""Nine Standards lifecycle gates per task Kanban transition.

Every task status transition must pass the standards checks defined
for that transition type before it is allowed to proceed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

ALL_STANDARDS = (
    "no-dead-code",
    "single-source-of-truth",
    "consistent-defaults",
    "minimal-surface-area",
    "defense-in-depth",
    "structural-honesty",
    "progressive-simplification",
    "deterministic-ordering",
    "inconsistent-elimination",
)

# Which standards to check for each transition.
# Keys are "from_status->to_status".
TRANSITION_GATES: dict[str, tuple[str, ...]] = {
    "backlog->ready": ("deterministic-ordering", "minimal-surface-area"),
    "ready->in_progress": ("no-dead-code", "single-source-of-truth"),
    "in_progress->ready": ("deterministic-ordering", "structural-honesty"),
    "in_progress->done": ALL_STANDARDS,
    "blocked->ready": ("no-dead-code", "single-source-of-truth"),
}

# Transitions that are always permitted (no standards gate).
PASSTHROUGH_TRANSITIONS = frozenset(
    {
        "in_progress->blocked",
        "blocked->in_progress",
        "done->archived",
        "archived->backlog",
    }
)


class GateResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class StandardGate:
    """Result of a single standard check during a transition."""

    standard: str
    result: GateResult
    detail: str = ""


@dataclass
class LifecycleGateReport:
    """Full report for a transition gate evaluation."""

    task_id: str
    from_status: str
    to_status: str
    allowed: bool
    reason: str = ""
    gates: list[StandardGate] = field(default_factory=list)
    rpe_event: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "gates": [
                {"standard": g.standard, "result": g.result.value, "detail": g.detail}
                for g in self.gates
            ],
            "rpe_event": self.rpe_event,
        }


def _build_transition_key(from_status: str, to_status: str) -> str:
    return f"{from_status}->{to_status}"


def evaluate_transition(
    task: dict[str, Any],
    from_status: str,
    to_status: str,
    standards_results: dict[str, GateResult] | None = None,
) -> LifecycleGateReport:
    """Evaluate whether a task can transition between two Kanban statuses.

    Args:
        task: The task dict (must have ``id``).
        from_status: Current kanban_status.
        to_status: Target kanban_status.
        standards_results: Pre-computed standards check results keyed by
            standard name. If omitted, all gates are skipped (dry-run mode).

    Returns:
        A *LifecycleGateReport* with the transition decision and per-standard details.
    """
    task_id = task.get("id", "?")
    key = _build_transition_key(from_status, to_status)

    # Passthrough transitions always allowed.
    if key in PASSTHROUGH_TRANSITIONS:
        detail = ""
        if from_status == "in_progress" and to_status == "blocked":
            detail = "blocking reason must be recorded"
        return LifecycleGateReport(
            task_id=task_id,
            from_status=from_status,
            to_status=to_status,
            allowed=True,
            reason=detail or f"transition {key} is always permitted",
        )

    # Look up required standards for this transition.
    required = TRANSITION_GATES.get(key)
    if required is None:
        return LifecycleGateReport(
            task_id=task_id,
            from_status=from_status,
            to_status=to_status,
            allowed=False,
            reason=f"transition {key} is not allowed",
        )

    # Evaluate each required standard.
    gates: list[StandardGate] = []
    any_fail = False

    if standards_results is None:
        # Dry-run: mark all as skip.
        for std in required:
            gates.append(
                StandardGate(standard=std, result=GateResult.SKIP, detail="no results provided")
            )
        return LifecycleGateReport(
            task_id=task_id,
            from_status=from_status,
            to_status=to_status,
            allowed=True,
            reason="dry-run: no standards results provided, all gates skipped",
            gates=gates,
        )

    for std in required:
        result = standards_results.get(std, GateResult.SKIP)
        detail = ""
        if result == GateResult.SKIP and std not in standards_results:
            detail = f"standard '{std}' not checked"
        gates.append(StandardGate(standard=std, result=result, detail=detail))
        if result == GateResult.FAIL:
            any_fail = True

    # Determine overall result.
    allowed = not any_fail

    reason_parts: list[str] = []
    if allowed:
        reason_parts.append(f"all {len(required)} standard(s) passed")
    else:
        failed = [g.standard for g in gates if g.result == GateResult.FAIL]
        warned = [g.standard for g in gates if g.result == GateResult.WARN]
        if failed:
            reason_parts.append(f"failed: {', '.join(failed)}")
        if warned:
            reason_parts.append(f"warned: {', '.join(warned)}")

    report = LifecycleGateReport(
        task_id=task_id,
        from_status=from_status,
        to_status=to_status,
        allowed=allowed,
        reason="; ".join(reason_parts),
        gates=gates,
    )

    # Attach RPE event on done transition.
    if to_status == "done" and allowed:
        from ocd.task_enforcer.rpe_bridge import build_rpe_from_task

        rpe_event = build_rpe_from_task(task, outcome=1.0)
        report.rpe_event = rpe_event.to_dict()

    return report
