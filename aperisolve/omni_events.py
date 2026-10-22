"""Redis pub/sub helpers for pushing full-mode task changes to WebSocket clients."""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from redis import Redis
from redis.client import PubSub
from redis.exceptions import RedisError

from .config import REDIS_URL

CHANNEL = "aperisolve:omni:events"
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _redis() -> Redis:
    return Redis.from_url(REDIS_URL)


def publish_event(task_id: str, event_type: str) -> None:
    """Publish a small invalidation event; task data remains in the task API."""
    try:
        _redis().publish(CHANNEL, json.dumps({"type": event_type, "task_id": task_id}))
    except RedisError:
        # Task execution must continue even if the UI event broker is temporarily down.
        logger.debug("Could not publish WebSocket update for task %s", task_id, exc_info=True)


def subscribe_events() -> PubSub:
    """Create a Redis subscription for the WebSocket route."""
    subscription = _redis().pubsub(ignore_subscribe_messages=True)
    subscription.subscribe(CHANNEL)
    return subscription
