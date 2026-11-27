"""Workspace event bus feeding Server-Sent Events (REQ-DR-6: live dashboard updates).

Publishers (API threads, Celery workers) push JSON events to the Redis channel of a
workspace; the SSE endpoint relays them to browsers. With the in-memory fallback,
events are delivered to subscribers in the same process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.kv import RedisStore, get_kv

logger = logging.getLogger(__name__)

_local_lock = threading.Lock()
_local_subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]]] = (
    defaultdict(set)
)


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
    for loop, queue in subscribers:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, message)
        except RuntimeError:  # loop closed
            continue


async def subscribe(
    workspace_id: uuid.UUID | str, heartbeat_seconds: float = 15.0
) -> AsyncIterator[str]:
    """Yield raw JSON messages for a workspace; yields "" as a heartbeat."""
    channel = channel_for(workspace_id)
    kv = get_kv()
    if isinstance(kv, RedisStore):
        import redis.asyncio as aioredis

        client = aioredis.Redis.from_url(get_settings().redis_url or "")
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=heartbeat_seconds
                )
                if msg is None:
                    yield ""
                    continue
                data = msg.get("data")
                yield data.decode() if isinstance(data, bytes) else str(data)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await client.aclose()
    else:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        entry = (loop, queue)
        with _local_lock:
            _local_subscribers[channel].add(entry)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    yield ""
        finally:
            with _local_lock:
                _local_subscribers[channel].discard(entry)
