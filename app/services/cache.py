"""A small two-level (memory + JSON file) cache with per-key TTLs.

Values must be JSON-serialisable. The interface (`get` / `set` / `fetch`) is
deliberately narrow so the file backend can later be swapped for Redis or a
database without touching the services that use it.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    stored_at: float
    expires_at: float

    @property
    def is_fresh(self) -> bool:
        return time.time() < self.expires_at


@dataclass
class CacheResult:
    value: Any
    stored_at: float
    stale: bool  # True when an expired entry was served because a refresh failed


class FileCache:
    def __init__(self, directory: Path | None):
        self._dir = directory
        self._memory: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path | None:
        if self._dir is None:
            return None
        readable = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:80]
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._dir / f"{readable}.{digest}.json"

    def get(self, key: str) -> CacheEntry | None:
        """Return the entry for `key`, fresh or expired, or None."""
        entry = self._memory.get(key)
        if entry is not None:
            return entry
        path = self._path(key)
        if path is None or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
            entry = CacheEntry(raw["value"], raw["stored_at"], raw["expires_at"])
        except (OSError, ValueError, KeyError) as exc:
            log.warning("ignoring unreadable cache file %s: %s", path, exc)
            return None
        self._memory[key] = entry
        return entry

    def set(self, key: str, value: Any, ttl: float) -> CacheEntry:
        now = time.time()
        entry = CacheEntry(value, now, now + ttl)
        self._memory[key] = entry
        path = self._path(key)
        if path is not None:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"key": key, "value": value, "stored_at": now, "expires_at": entry.expires_at}))
            tmp.replace(path)
        return entry

    async def fetch(self, key: str, ttl: float, loader: Callable[[], Awaitable[Any]]) -> CacheResult:
        """Return a fresh cached value, or call `loader` to refresh it.

        Concurrent callers for the same key share one `loader` call. If the
        loader fails and an expired value exists, the expired value is served
        and flagged as stale rather than failing the request.
        """
        entry = self.get(key)
        if entry is not None and entry.is_fresh:
            return CacheResult(entry.value, entry.stored_at, stale=False)

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self.get(key)  # another caller may have refreshed it meanwhile
            if entry is not None and entry.is_fresh:
                return CacheResult(entry.value, entry.stored_at, stale=False)
            try:
                value = await loader()
            except Exception:
                if entry is not None:
                    log.warning("refresh of %s failed; serving stale value", key, exc_info=True)
                    return CacheResult(entry.value, entry.stored_at, stale=True)
                raise
            new = self.set(key, value, ttl)
            return CacheResult(new.value, new.stored_at, stale=False)

    def prune(self, keep_expired_for: float) -> int:
        """Delete cache files that expired more than `keep_expired_for` seconds ago."""
        if self._dir is None:
            return 0
        removed = 0
        cutoff = time.time() - keep_expired_for
        for path in self._dir.glob("*.json"):
            try:
                if json.loads(path.read_text()).get("expires_at", 0) < cutoff:
                    path.unlink()
                    removed += 1
            except (OSError, ValueError):
                continue
        return removed
