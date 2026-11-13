"""in-process response cache for the detail endpoints"""

import hashlib
import json
import logging
from collections import OrderedDict
from os import environ
from time import monotonic
from typing import Any, Callable

from fastapi import Request, Response, status

logger = logging.getLogger(__name__)

CACHE_CONTROL = "public, max-age=60"
DEFAULT_MAX_ENTRIES = 20_000
DEFAULT_TTL_SECONDS = 300.0

CacheEntry = tuple[dict[str, Any], str]


class TTLCache:
    """small LRU cache with a per-entry time to live"""

    def __init__(
        self,
        max_entries: int,
        ttl_seconds: float,
        clock: Callable[[], float] = monotonic,
    ):
        self.max_entries = max(0, max_entries)
        self.ttl_seconds = max(0.0, ttl_seconds)
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        """return a live entry and mark it as recently used"""
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= self._clock():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        """store an entry, evicting the least recently used one if needed"""
        if self.max_entries == 0:
            return
        self._entries[key] = (self._clock() + self.ttl_seconds, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """drop every entry, e.g. after an import"""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


def _env_int(name: str, default: int) -> int:
    """read an integer env var without failing the app on a typo"""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid %s=%r, using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    """read a float env var without failing the app on a typo"""
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid %s=%r, using %s", name, raw, default)
        return default


response_cache: TTLCache = TTLCache(
    max_entries=_env_int("API_CACHE_ENTRIES", DEFAULT_MAX_ENTRIES),
    ttl_seconds=_env_float("API_CACHE_TTL_SECONDS", DEFAULT_TTL_SECONDS),
)


def make_etag(payload: Any) -> str:
    """stable weak ETag for a JSON payload"""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f'W/"{digest}"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """compare an If-None-Match header with an ETag (weak comparison)"""
    if not if_none_match:
        return False
    candidates = [candidate.strip() for candidate in if_none_match.split(",")]
    if "*" in candidates:
        return True
    normalized = etag.removeprefix("W/")
    return any(candidate.removeprefix("W/") == normalized for candidate in candidates)


def finalize_cached_response(
    request: Request,
    response: Response,
    entry: CacheEntry,
) -> dict[str, Any] | Response:
    """add validators and answer 304 when the client already has this payload"""
    payload, etag = entry
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return payload


def invalidate_response_cache() -> None:
    """drop every cached detail response (called after an import)"""
    response_cache.clear()
