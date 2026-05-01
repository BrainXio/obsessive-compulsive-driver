"""Tests for stale task pruning."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ocd.task_enforcer.pruning import (
    _compute_age_days,
    _decay_score,
    archived_stale_tasks,
    find_stale_tasks,
)


def _old_date(days_ago: int) -> str:
    """Return an ISO date string from *days_ago* days in the past."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _tasks_json(pending: list[dict]) -> dict:
    return {"pending": pending}


class TestDecayScore:
    def test_fresh_task_retains_most_value(self):
        score = _decay_score(100, 0)
        assert score == 100

    def test_60_day_old_task_decays_to_roughly_half(self):
        score = _decay_score(100, 60)
        assert 40 < score < 65

    def test_very_old_task_approaches_zero(self):
        score = _decay_score(100, 1000)
        assert score < 10


class TestComputeAgeDays:
    def test_returns_none_when_no_last_updated(self):
        assert _compute_age_days({}) is None

    def test_returns_age_for_valid_iso_string(self):
        dt = datetime.now(UTC) - timedelta(days=10)
        task = {"last_updated": dt.isoformat()}
        age = _compute_age_days(task)
        assert age is not None
        assert 9.5 < age < 10.5

    def test_returns_none_for_invalid_date_string(self):
        assert _compute_age_days({"last_updated": "not-a-date"}) is None

    def test_handles_z_suffix(self):
        dt = datetime.now(UTC) - timedelta(days=5)
        task = {"last_updated": dt.isoformat().replace("+00:00", "Z")}
        age = _compute_age_days(task)
        assert age is not None
        assert 4.5 < age < 5.5


class TestFindStaleTasks:
    def test_empty_pending_returns_no_stale(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([])))
        report = find_stale_tasks(path)
        assert report.analyzed == 0
        assert report.stale == []

    def test_non_backlog_task_is_skipped(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "Active task",
            "kanban_status": "in_progress",
            "priority": {"level": 3, "value_score": 40, "rpe_weight": 0.5},
            "last_updated": _old_date(60),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert report.stale == []

    def test_high_value_task_is_skipped(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "Valuable task",
            "kanban_status": "backlog",
            "priority": {"level": 3, "value_score": 80, "rpe_weight": 0.5},
            "last_updated": _old_date(60),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert report.stale == []

    def test_high_priority_task_is_skipped(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "P1 task",
            "kanban_status": "backlog",
            "priority": {"level": 1, "value_score": 40, "rpe_weight": 0.5},
            "last_updated": _old_date(60),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert report.stale == []

    def test_recent_task_is_skipped(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "Recent task",
            "kanban_status": "backlog",
            "priority": {"level": 3, "value_score": 40, "rpe_weight": 0.5},
            "last_updated": _old_date(5),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert report.stale == []

    def test_stale_task_is_flagged(self, tmp_path: Path):
        task = {
            "id": "ocd-old",
            "subject": "Forgotten task",
            "kanban_status": "backlog",
            "priority": {"level": 3, "value_score": 30, "rpe_weight": 0.3},
            "last_updated": _old_date(45),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert len(report.stale) == 1
        s = report.stale[0]
        assert s.task_id == "ocd-old"
        assert s.decayed_score is not None
        assert s.decayed_score < 30

    def test_multiple_stale_tasks(self, tmp_path: Path):
        tasks = []
        for i in range(3):
            tasks.append(
                {
                    "id": f"ocd-old-{i}",
                    "subject": f"Stale {i}",
                    "kanban_status": "backlog",
                    "priority": {"level": 3, "value_score": 30, "rpe_weight": 0.3},
                    "last_updated": _old_date(45 + i),
                }
            )
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json(tasks)))
        report = find_stale_tasks(path)
        assert len(report.stale) == 3

    def test_defaults_backlog_when_status_missing(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "No status",
            "priority": {"level": 3, "value_score": 30, "rpe_weight": 0.3},
            "last_updated": _old_date(45),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert len(report.stale) == 1

    def test_numeric_priority_fallback(self, tmp_path: Path):
        task = {
            "id": "ocd-1",
            "subject": "Numeric priority",
            "kanban_status": "backlog",
            "priority": 4,
            "last_updated": _old_date(45),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert len(report.stale) == 1

    def test_suggestions_include_human_review(self, tmp_path: Path):
        task = {
            "id": "ocd-old",
            "subject": "Stale",
            "kanban_status": "backlog",
            "priority": {"level": 3, "value_score": 30, "rpe_weight": 0.3},
            "last_updated": _old_date(45),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        report = find_stale_tasks(path)
        assert any("Human review" in s for s in report.suggestions)

    def test_no_stale_suggestion(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([])))
        report = find_stale_tasks(path)
        assert any("No stale" in s for s in report.suggestions)


class TestArchivedStaleTasks:
    def test_no_stale_no_modification(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        original = json.dumps(_tasks_json([]))
        path.write_text(original)
        archived_stale_tasks(path)
        assert path.read_text() == original

    def test_archives_stale_tasks(self, tmp_path: Path):
        task = {
            "id": "ocd-old",
            "subject": "Stale task",
            "kanban_status": "backlog",
            "priority": {"level": 3, "value_score": 30, "rpe_weight": 0.3},
            "last_updated": _old_date(45),
        }
        path = tmp_path / "tasks.json"
        path.write_text(json.dumps(_tasks_json([task])))
        archived_stale_tasks(path)
        data = json.loads(path.read_text())
        assert data["pending"][0]["kanban_status"] == "archived"
        assert "_archived_reason" in data["pending"][0]
        assert "_archived_date" in data["pending"][0]
