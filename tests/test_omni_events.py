"""WebSocket invalidation messages for task and branch updates."""

import json

import pytest

from aperisolve import omni_events


def test_log_events_include_the_branch_and_generic_events_remain_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clients can filter branch logs while still receiving task-wide events."""
    messages: list[tuple[str, dict]] = []

    class FakeRedis:
        def publish(self, channel: str, message: str) -> None:
            messages.append((channel, json.loads(message)))

    monkeypatch.setattr(omni_events, "_redis", FakeRedis)
    omni_events.publish_event("task", "log_changed", solver="pi-1")
    omni_events.publish_event("task", "task_changed")

    assert messages == [
        (omni_events.CHANNEL, {"type": "log_changed", "task_id": "task", "solver": "pi-1"}),
        (omni_events.CHANNEL, {"type": "task_changed", "task_id": "task"}),
    ]
