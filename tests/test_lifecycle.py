"""Tests for Nine Standards lifecycle gates."""

from __future__ import annotations

from ocd.task_enforcer.lifecycle import (
    ALL_STANDARDS,
    PASSTHROUGH_TRANSITIONS,
    TRANSITION_GATES,
    GateResult,
    LifecycleGateReport,
    StandardGate,
    evaluate_transition,
)


class TestTransitionGates:
    def test_backlog_to_ready_checks_deterministic_and_minimal(self):
        gates = TRANSITION_GATES["backlog->ready"]
        assert "deterministic-ordering" in gates
        assert "minimal-surface-area" in gates
        assert len(gates) == 2

    def test_in_progress_to_done_checks_all_nine(self):
        assert TRANSITION_GATES["in_progress->done"] == ALL_STANDARDS

    def test_passthrough_includes_block_transitions(self):
        assert "in_progress->blocked" in PASSTHROUGH_TRANSITIONS
        assert "blocked->in_progress" in PASSTHROUGH_TRANSITIONS
        assert "done->archived" in PASSTHROUGH_TRANSITIONS
        assert "archived->backlog" in PASSTHROUGH_TRANSITIONS


class TestEvaluateTransition:
    def _task(self):
        return {"id": "ocd-13", "subject": "Lifecycle gates", "description": "Implement"}

    # ── Passthrough transitions ──

    def test_in_progress_to_blocked_always_allowed(self):
        report = evaluate_transition(self._task(), "in_progress", "blocked")
        assert report.allowed is True
        assert "blocking reason" in report.reason

    def test_blocked_to_in_progress_always_allowed(self):
        report = evaluate_transition(self._task(), "blocked", "in_progress")
        assert report.allowed is True

    def test_done_to_archived_always_allowed(self):
        report = evaluate_transition(self._task(), "done", "archived")
        assert report.allowed is True

    def test_archived_to_backlog_always_allowed(self):
        report = evaluate_transition(self._task(), "archived", "backlog")
        assert report.allowed is True

    # ── Unknown / invalid transitions ──

    def test_unknown_transition_rejected(self):
        report = evaluate_transition(self._task(), "done", "backlog")
        assert report.allowed is False
        assert "not allowed" in report.reason

    # ── Dry-run (no standards results) ──

    def test_dry_run_allows_transition_with_skip(self):
        report = evaluate_transition(self._task(), "backlog", "ready")
        assert report.allowed is True
        assert "dry-run" in report.reason
        assert all(g.result == GateResult.SKIP for g in report.gates)

    # ── With real standards results ──

    def test_all_pass_allows_transition(self):
        results = {
            "deterministic-ordering": GateResult.PASS,
            "minimal-surface-area": GateResult.PASS,
        }
        report = evaluate_transition(self._task(), "backlog", "ready", results)
        assert report.allowed is True
        assert all(g.result == GateResult.PASS for g in report.gates)

    def test_single_fail_blocks_transition(self):
        results = {
            "deterministic-ordering": GateResult.PASS,
            "minimal-surface-area": GateResult.FAIL,
        }
        report = evaluate_transition(self._task(), "backlog", "ready", results)
        assert report.allowed is False
        assert any(g.result == GateResult.FAIL for g in report.gates)

    def test_warn_does_not_block_transition(self):
        results = {
            "deterministic-ordering": GateResult.WARN,
            "minimal-surface-area": GateResult.PASS,
        }
        report = evaluate_transition(self._task(), "backlog", "ready", results)
        assert report.allowed is True

    def test_missing_standard_marked_as_skip(self):
        results = {"deterministic-ordering": GateResult.PASS}
        report = evaluate_transition(self._task(), "backlog", "ready", results)
        assert report.allowed is True
        skipped = [g for g in report.gates if g.result == GateResult.SKIP]
        assert len(skipped) == 1

    # ── RPE events ──

    def test_done_transition_attaches_rpe_event(self):
        results = {s: GateResult.PASS for s in ALL_STANDARDS}
        report = evaluate_transition(self._task(), "in_progress", "done", results)
        assert report.allowed is True
        assert report.rpe_event is not None
        assert report.rpe_event["task_id"] == "ocd-13"
        assert report.rpe_event["outcome"] == 1.0

    def test_done_transition_failed_no_rpe_event(self):
        results = {s: GateResult.PASS for s in ALL_STANDARDS}
        results["no-dead-code"] = GateResult.FAIL
        report = evaluate_transition(self._task(), "in_progress", "done", results)
        assert report.allowed is False
        assert report.rpe_event is None


class TestLifecycleGateReport:
    def test_to_dict_includes_all_fields(self):
        report = LifecycleGateReport(
            task_id="ocd-1",
            from_status="backlog",
            to_status="ready",
            allowed=True,
            reason="all passed",
            gates=[
                StandardGate(
                    standard="deterministic-ordering", result=GateResult.PASS, detail="ok"
                ),
            ],
            rpe_event={"task_id": "ocd-1", "outcome": 1.0},
        )
        d = report.to_dict()
        assert d["task_id"] == "ocd-1"
        assert d["from_status"] == "backlog"
        assert d["to_status"] == "ready"
        assert d["allowed"] is True
        assert d["reason"] == "all passed"
        assert len(d["gates"]) == 1
        assert d["gates"][0]["standard"] == "deterministic-ordering"
        assert d["gates"][0]["result"] == "pass"
        assert d["rpe_event"] is not None
