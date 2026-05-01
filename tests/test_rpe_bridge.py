"""Tests for RPE bridge between OCD task completion and AI Critic."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ocd.task_enforcer.rpe_bridge import (
    RpeEvent,
    build_rpe_from_task,
)


class TestRpeEvent:
    def test_to_dict_includes_all_fields(self):
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        event = RpeEvent(
            task_id="ocd-10",
            outcome=0.85,
            context="Integrated RPE telemetry",
            timestamp=ts,
        )
        d = event.to_dict()
        assert d["task_id"] == "ocd-10"
        assert d["outcome"] == 0.85
        assert d["context"] == "Integrated RPE telemetry"
        assert d["timestamp"] == ts.isoformat()
        assert d["source"] == "ocd-task-enforcer"

    def test_default_timestamp_is_utc_now(self):
        event = RpeEvent(task_id="ocd-1", outcome=1.0, context="test")
        assert event.timestamp.tzinfo == UTC
        assert (datetime.now(UTC) - event.timestamp).total_seconds() < 5

    def test_to_preference_pair_matches_ai_schema(self):
        ts = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        event = RpeEvent(
            task_id="ocd-10",
            outcome=0.85,
            context="Integrated RPE telemetry",
            timestamp=ts,
        )
        pair = event.to_preference_pair()
        assert pair["context"] == "[ocd-10] Integrated RPE telemetry"
        assert pair["chosen"] == "completed:ocd-10"
        assert pair["rejected"] == ["abandoned:ocd-10"]
        assert pair["rpe"] == 0.85
        assert pair["timestamp"] == ts.isoformat()

    def test_to_bus_payload_is_valid_json(self):
        event = RpeEvent(task_id="ocd-1", outcome=1.0, context="test")
        payload_str = event.to_bus_payload()
        payload = json.loads(payload_str)
        assert payload["type"] == "event"
        assert payload["topic"] == "rpe-event"
        assert "task_id" in payload["payload"]
        assert "preference_pair" in payload["payload"]

    def test_to_bus_payload_preference_pair_embedded(self):
        event = RpeEvent(task_id="ocd-10", outcome=0.5, context="test")
        payload = json.loads(event.to_bus_payload())
        pp = payload["payload"]["preference_pair"]
        assert pp["chosen"] == "completed:ocd-10"
        assert pp["rpe"] == 0.5


class TestBuildRpeFromTask:
    def test_builds_from_complete_task_dict(self):
        task = {
            "id": "ocd-10",
            "subject": "Integrate RPE telemetry",
            "description": "Publish RPE events on task completion",
        }
        event = build_rpe_from_task(task, 0.9)
        assert event.task_id == "ocd-10"
        assert event.outcome == 0.9
        assert event.context == "Integrate RPE telemetry"

    def test_fallback_to_description_when_no_subject(self):
        task = {"id": "ocd-99", "description": "No subject here"}
        event = build_rpe_from_task(task, 0.5)
        assert event.context == "No subject here"

    def test_fallback_to_generic_when_no_subject_or_description(self):
        task = {"id": "ocd-unknown"}
        event = build_rpe_from_task(task, 0.3)
        assert "Task ocd-unknown completed" in event.context

    def test_negative_outcome_allowed(self):
        task = {"id": "ocd-fail", "subject": "Failed task"}
        event = build_rpe_from_task(task, -0.5)
        assert event.outcome == -0.5
