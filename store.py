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

    def exists(self, *keys: str) -> int:
        count = 0
        for key in keys:
            self._expire_if_due(key)
            if key in self._data:
                count += 1
        return count

    def _add_to_int(self, key: str, delta: int) -> int:
        self._expire_if_due(key)
        try:
            current = int(self._data.get(key, "0"))
        except ValueError:
            raise ValueError("value is not an integer or out of range")
        new_value = current + delta
        self._data[key] = str(new_value)
        return new_value

    def incr(self, key: str) -> int:
        return self._add_to_int(key, 1)

    def decr(self, key: str) -> int:
        return self._add_to_int(key, -1)

    def append(self, key: str, value: str) -> int:
        self._expire_if_due(key)
        new_value = self._data.get(key, "") + value
        self._data[key] = new_value
        return len(new_value)

    def mset(self, items: dict[str, str]) -> None:
        for key, value in items.items():
            self.set(key, value)

    def mget(self, *keys: str) -> list[str | None]:
        return [self.get(key) for key in keys]

    def type(self, key: str) -> str:
        self._expire_if_due(key)
        return "string" if key in self._data else "none"


async def run_active_expiration(store: Store, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        store.sweep_expired()
