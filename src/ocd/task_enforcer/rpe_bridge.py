"""RPE bridge between OCD task completion and the Another-Intelligence Critic.

Publishes structured Reward Prediction Error events so the AI Dopamine
system can discover and consume them for preference-pair dataset generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class RpeEvent:
    """An RPE signal emitted when a task reaches a terminal state.

    Compatible with :class:`another_intelligence.memory.PreferencePair`
    format so the AI Critic can generate QLoRA training pairs directly.
    """

    task_id: str
    outcome: float
    context: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "ocd-task-enforcer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "outcome": self.outcome,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }

    def to_preference_pair(self) -> dict[str, Any]:
        """Convert to a dict matching AI's ``PreferencePair`` schema.

        The chosen action is task completion; the implicit rejected
        alternative is abandonment or indefinite deferral.
        """
        return {
            "context": f"[{self.task_id}] {self.context}",
            "chosen": f"completed:{self.task_id}",
            "rejected": [f"abandoned:{self.task_id}"],
            "rpe": self.outcome,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_bus_payload(self) -> str:
        """Return a JSON string payload for ``adhd_post`` with topic ``rpe-event``."""
        import json

        return json.dumps(
            {
                "type": "event",
                "topic": "rpe-event",
                "payload": {
                    "task_id": self.task_id,
                    "outcome": self.outcome,
                    "context": self.context,
                    "timestamp": self.timestamp.isoformat(),
                    "source": self.source,
                    "preference_pair": self.to_preference_pair(),
                },
            }
        )


def build_rpe_from_task(task: dict[str, Any], outcome: float) -> RpeEvent:
    """Build an *RpeEvent* from a completed task dict and outcome value.

    Args:
        task: A task dict with at least ``id`` and ``subject`` keys.
        outcome: Outcome value on a 0.0–1.0 scale (1.0 = perfect success).

    Returns:
        An *RpeEvent* ready for publishing or preference-pair conversion.
    """
    task_id = task.get("id", "unknown")
    subject = task.get("subject", "")
    description = task.get("description", "")
    context = subject or description or f"Task {task_id} completed"
    return RpeEvent(task_id=task_id, outcome=outcome, context=context)
