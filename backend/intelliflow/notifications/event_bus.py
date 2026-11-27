"""Workspace event bus feeding Server-Sent Events (REQ-DR-6: live dashboard updates).

Publishers (API requests, Celery workers) push JSON events to the Redis channel of a
workspace; the SSE view relays them to browsers. Without Redis (development and
tests) events reach subscribers in the same process through thread-safe queues.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import redis
from django.conf import settings

from intelliflow.core.kv import RedisStore, get_kv

logger = logging.getLogger(__name__)

_local_lock = threading.Lock()
_local_subscribers: dict[str, set[queue.Queue[str]]] = defaultdict(set)


def channel_for(workspace_id: uuid.UUID | str) -> str:
    return f"intelliflow:ws:{workspace_id}"


def publish(
    workspace_id: uuid.UUID | str, event_type: str, data: dict[str, Any] | None = None
) -> None:
    message = json.dumps(
        {"type": event_type, "data": data or {}, "ts": datetime.now(UTC).isoformat()}, default=str
    )
    try:
        get_kv().publish(channel_for(workspace_id), message)
    except Exception:  # live updates are best-effort and must never break a run
        logger.warning("event publish failed", extra={"event_type": event_type})


def local_broadcast(channel: str, message: str) -> None:
    with _local_lock:
        subscribers = list(_local_subscribers.get(channel, ()))
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(message)
        except queue.Full:  # a stalled browser must not block publishers
            continue


def subscribe(workspace_id: uuid.UUID | str, heartbeat_seconds: float = 15.0) -> Iterator[str]:
    """Yield raw JSON messages for a workspace; yields "" as a heartbeat.

    The generator holds one thread while a browser is connected (Gunicorn threads);
    closing it (client disconnect) unsubscribes."""
    channel = channel_for(workspace_id)
    if isinstance(get_kv(), RedisStore):
        client = redis.Redis.from_url(settings.REDIS_URL or "", socket_connect_timeout=2)
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)
        try:
            while True:
                msg = pubsub.get_message(timeout=heartbeat_seconds)
                if msg is None:
                    yield ""
                    continue
                data = msg.get("data")
                yield data.decode() if isinstance(data, bytes) else str(data)
        finally:
            pubsub.close()
            client.close()
    else:
        subscriber: queue.Queue[str] = queue.Queue(maxsize=1000)
        with _local_lock:
            _local_subscribers[channel].add(subscriber)
        try:
            while True:
                try:
                    yield subscriber.get(timeout=heartbeat_seconds)
                except queue.Empty:
                    yield ""
        finally:
            with _local_lock:
                _local_subscribers[channel].discard(subscriber)
