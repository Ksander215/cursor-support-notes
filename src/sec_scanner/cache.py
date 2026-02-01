"""Redis cache module for sec-scanner API.

This module provides caching for frequently accessed data:
- Completed audit results (immutable after completion)
- Quota information (TTL-based, invalidated on changes)
- Audit lists (short TTL for freshness)

Cache keys follow the pattern: sec_scanner:{type}:{identifier}
"""

import json
import logging
import os
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

import redis

logger = logging.getLogger("sec_scanner.cache")

# Type variable for generic return type
T = TypeVar("T")

# Cache TTLs
CACHE_TTL_AUDIT_RESULT = timedelta(hours=24)  # Completed audits are immutable
CACHE_TTL_QUOTA = timedelta(minutes=5)  # Quota info refreshed frequently
CACHE_TTL_AUDIT_LIST = timedelta(seconds=30)  # Lists are very dynamic
CACHE_TTL_AUDIT_HISTORY = timedelta(minutes=10)  # Historical data changes less

# Cache key prefixes
KEY_PREFIX = "sec_scanner"
KEY_AUDIT = f"{KEY_PREFIX}:audit"
KEY_QUOTA = f"{KEY_PREFIX}:quota"
KEY_AUDIT_LIST = f"{KEY_PREFIX}:audit_list"
KEY_AUDIT_HISTORY = f"{KEY_PREFIX}:audit_history"


def get_redis_url() -> str:
    """Get Redis URL from environment."""
    return os.getenv("SEC_SCANNER_REDIS_URL", "").strip()


def get_redis_client() -> redis.Redis | None:
    """
    Get Redis client for caching.
    Returns None if Redis is not configured.
    """
    url = get_redis_url()
    if not url:
        return None

    try:
        client = redis.from_url(url, decode_responses=True)
        # Test connection
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis for caching: {e}")
        return None


class CacheManager:
    """
    Centralized cache manager with lazy Redis connection.
    Thread-safe and handles Redis unavailability gracefully.
    """

    _instance: "CacheManager | None" = None
    _client: redis.Redis | None = None
    _initialized: bool = False

    def __new__(cls) -> "CacheManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_client(self) -> redis.Redis | None:
        """Lazy initialization of Redis client."""
        if not self._initialized:
            self._client = get_redis_client()
            self._initialized = True
            if self._client:
                logger.info("Cache manager connected to Redis")
            else:
                logger.info("Cache manager: Redis not available, caching disabled")
        return self._client

    @property
    def enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._get_client() is not None

    def get(self, key: str) -> Any | None:
        """Get value from cache."""
        client = self._get_client()
        if not client:
            return None

        try:
            data = client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.debug(f"Cache get failed for {key}: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: timedelta | int | None = None,
    ) -> bool:
        """Set value in cache with optional TTL."""
        client = self._get_client()
        if not client:
            return False

        try:
            data = json.dumps(value, default=str)
            if ttl:
                if isinstance(ttl, timedelta):
                    ttl = int(ttl.total_seconds())
                client.setex(key, ttl, data)
            else:
                client.set(key, data)
            return True
        except Exception as e:
            logger.debug(f"Cache set failed for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        client = self._get_client()
        if not client:
            return False

        try:
            client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete failed for {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        client = self._get_client()
        if not client:
            return 0

        try:
            keys = list(client.scan_iter(match=pattern, count=100))
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            logger.debug(f"Cache delete_pattern failed for {pattern}: {e}")
            return 0

    def invalidate_audit(self, audit_id: str) -> None:
        """Invalidate all caches related to an audit."""
        self.delete(f"{KEY_AUDIT}:{audit_id}")
        # Also invalidate lists that might contain this audit
        self.delete_pattern(f"{KEY_AUDIT_LIST}:*")

    def invalidate_tenant_caches(self, tenant_id: int) -> None:
        """Invalidate all caches for a tenant."""
        self.delete(f"{KEY_QUOTA}:{tenant_id}")
        self.delete_pattern(f"{KEY_AUDIT_LIST}:tenant:{tenant_id}:*")
        self.delete_pattern(f"{KEY_AUDIT_HISTORY}:tenant:{tenant_id}:*")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        client = self._get_client()
        if not client:
            return {"enabled": False}

        try:
            info = client.info("stats")
            return {
                "enabled": True,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "keys": client.dbsize(),
            }
        except Exception as e:
            return {"enabled": True, "error": str(e)}


# Global cache manager instance
cache = CacheManager()


# --- Cache key builders ---


def audit_key(audit_id: str) -> str:
    """Build cache key for audit result."""
    return f"{KEY_AUDIT}:{audit_id}"


def quota_key(tenant_id: int) -> str:
    """Build cache key for quota info."""
    return f"{KEY_QUOTA}:{tenant_id}"


def audit_list_key(
    tenant_id: int | None = None,
    limit: int = 50,
    status: str | None = None,
) -> str:
    """Build cache key for audit list."""
    parts = [KEY_AUDIT_LIST]
    if tenant_id is not None:
        parts.append(f"tenant:{tenant_id}")
    else:
        parts.append("global")
    parts.append(f"limit:{limit}")
    if status:
        parts.append(f"status:{status}")
    return ":".join(parts)


def audit_history_key(
    target: str,
    tenant_id: int | None = None,
    limit: int = 50,
) -> str:
    """Build cache key for audit history."""
    # Normalize target for key (remove special chars)
    safe_target = target.replace(":", "_").replace("/", "_")[:50]
    parts = [KEY_AUDIT_HISTORY]
    if tenant_id is not None:
        parts.append(f"tenant:{tenant_id}")
    else:
        parts.append("global")
    parts.append(f"target:{safe_target}")
    parts.append(f"limit:{limit}")
    return ":".join(parts)


# --- Cached DB functions ---


def get_cached_audit(audit_id: str, fetch_fn: Callable[[], dict | None]) -> dict | None:
    """
    Get audit from cache or fetch from DB.
    Only caches completed audits (they are immutable).
    """
    # Try cache first
    cached = cache.get(audit_key(audit_id))
    if cached is not None:
        logger.debug(f"Cache HIT for audit {audit_id}")
        return cached

    # Fetch from DB
    result = fetch_fn()
    if result is None:
        return None

    # Only cache completed audits (they won't change)
    if result.get("status") == "completed":
        cache.set(audit_key(audit_id), result, CACHE_TTL_AUDIT_RESULT)
        logger.debug(f"Cached audit {audit_id}")

    return result


def get_cached_quota(
    tenant_id: int,
    fetch_fn: Callable[[], dict | None],
) -> dict | None:
    """
    Get quota info from cache or fetch from DB.
    Short TTL as quota can change with usage.
    """
    key = quota_key(tenant_id)

    # Try cache first
    cached = cache.get(key)
    if cached is not None:
        logger.debug(f"Cache HIT for quota tenant:{tenant_id}")
        return cached

    # Fetch from DB
    result = fetch_fn()
    if result is None:
        return None

    # Cache with short TTL
    cache.set(key, result, CACHE_TTL_QUOTA)
    logger.debug(f"Cached quota for tenant:{tenant_id}")

    return result


def get_cached_audit_list(
    tenant_id: int | None,
    limit: int,
    status: str | None,
    fetch_fn: Callable[[], tuple[list, bool, int | None]],
) -> tuple[list, bool, int | None]:
    """
    Get audit list from cache or fetch from DB.
    Very short TTL as lists are dynamic.
    """
    key = audit_list_key(tenant_id, limit, status)

    # Try cache first
    cached = cache.get(key)
    if cached is not None:
        logger.debug("Cache HIT for audit list")
        return cached["items"], cached["has_more"], cached.get("total")

    # Fetch from DB
    items, has_more, total = fetch_fn()

    # Cache result
    cache.set(key, {"items": items, "has_more": has_more, "total": total}, CACHE_TTL_AUDIT_LIST)
    logger.debug("Cached audit list")

    return items, has_more, total


def get_cached_audit_history(
    target: str,
    tenant_id: int | None,
    limit: int,
    fetch_fn: Callable[[], list],
) -> list:
    """
    Get audit history from cache or fetch from DB.
    """
    key = audit_history_key(target, tenant_id, limit)

    # Try cache first
    cached = cache.get(key)
    if cached is not None:
        logger.debug(f"Cache HIT for audit history target:{target}")
        return cached

    # Fetch from DB
    result = fetch_fn()

    # Cache result
    cache.set(key, result, CACHE_TTL_AUDIT_HISTORY)
    logger.debug(f"Cached audit history for target:{target}")

    return result


# --- Cache invalidation helpers ---


def invalidate_on_audit_update(audit_id: str, tenant_id: int | None = None) -> None:
    """Call this when an audit is updated."""
    cache.invalidate_audit(audit_id)
    if tenant_id:
        # Also invalidate lists for this tenant
        cache.delete_pattern(f"{KEY_AUDIT_LIST}:tenant:{tenant_id}:*")


def invalidate_on_quota_change(tenant_id: int) -> None:
    """Call this when quota or usage changes."""
    cache.delete(quota_key(tenant_id))


def invalidate_on_new_audit(tenant_id: int | None = None) -> None:
    """Call this when a new audit is created."""
    if tenant_id:
        cache.delete_pattern(f"{KEY_AUDIT_LIST}:tenant:{tenant_id}:*")
    else:
        cache.delete_pattern(f"{KEY_AUDIT_LIST}:*")
