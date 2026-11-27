"""Small key-value facade over Redis 7 (de-duplication, rate limits, locks, windows).

Falls back to a thread-safe in-memory store when Redis is unavailable in development
and tests, so the prototype runs with zero infrastructure. Production refuses the
fallback, because de-duplication must be shared by every API and worker process.
"""

from __future__ import annotations

import logging
import threading
import time
from functools import lru_cache
from typing import Protocol

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


class KeyValueStore(Protocol):
    def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool: ...
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr(self, key: str, ttl_seconds: int) -> int: ...
    def publish(self, channel: str, message: str) -> None: ...


class RedisStore:
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        return bool(self.client.set(key, value, nx=True, ex=ttl_seconds))

    def get(self, key: str) -> str | None:
        value = self.client.get(key)
        return value.decode() if isinstance(value, bytes) else value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self.client.set(key, value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def incr(self, key: str, ttl_seconds: int) -> int:
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_seconds, nx=True)
        count, _ = pipe.execute()
        return int(count)

    def publish(self, channel: str, message: str) -> None:
        self.client.publish(channel, message)


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = threading.Lock()
        self.subscribers: list[object] = []

    def _alive(self, key: str) -> tuple[str, float | None] | None:
        item = self._data.get(key)
        if item and item[1] is not None and item[1] < time.monotonic():
            del self._data[key]
            return None
        return item

    def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        with self._lock:
            if self._alive(key):
                return False
            self._data[key] = (value, time.monotonic() + ttl_seconds)
            return True

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._alive(key)
            return item[0] if item else None

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl_seconds if ttl_seconds else None)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl_seconds: int) -> int:
        with self._lock:
            item = self._alive(key)
            count = int(item[0]) + 1 if item else 1
            expiry = item[1] if item else time.monotonic() + ttl_seconds
            self._data[key] = (str(count), expiry)
            return count

    def publish(self, channel: str, message: str) -> None:
        from intelliflow.notifications.event_bus import local_broadcast

        local_broadcast(channel, message)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


@lru_cache(maxsize=1)
def get_kv() -> KeyValueStore:
    if settings.REDIS_URL:
        try:
            client = redis.Redis.from_url(
                settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2
            )
            client.ping()
            return RedisStore(client)
        except redis.RedisError as exc:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Redis is required in production") from exc
            logger.warning("Redis unavailable (%s); using in-memory store", exc.__class__.__name__)
    return MemoryStore()


def reset_kv() -> None:
    get_kv.cache_clear()
