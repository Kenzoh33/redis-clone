"""In-memory key-value store."""

import asyncio
import time
from typing import Callable


class Store:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._data: dict[str, str] = {}
        self._expires_at: dict[str, float] = {}
        self._clock = clock

    def _expire_if_due(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is not None and expires_at <= self._clock():
            self._data.pop(key, None)
            self._expires_at.pop(key, None)

    def get(self, key: str) -> str | None:
        self._expire_if_due(key)
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._expires_at.pop(key, None)

    def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            self._expire_if_due(key)
            if key in self._data:
                del self._data[key]
                self._expires_at.pop(key, None)
                count += 1
        return count

    def expire(self, key: str, seconds: float) -> bool:
        self._expire_if_due(key)
        if key not in self._data:
            return False
        if seconds <= 0:
            del self._data[key]
            self._expires_at.pop(key, None)
        else:
            self._expires_at[key] = self._clock() + seconds
        return True

    def ttl(self, key: str) -> int:
        self._expire_if_due(key)
        if key not in self._data:
            return -2
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return -1
        return max(0, int(expires_at - self._clock()))

    def sweep_expired(self) -> int:
        now = self._clock()
        expired_keys = [key for key, expires_at in self._expires_at.items() if expires_at <= now]
        for key in expired_keys:
            self._data.pop(key, None)
            self._expires_at.pop(key, None)
        return len(expired_keys)


async def run_active_expiration(store: Store, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        store.sweep_expired()
