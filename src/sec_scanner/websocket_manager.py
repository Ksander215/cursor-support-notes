"""WebSocket manager with Redis Pub/Sub for real-time progress updates.

This module provides:
- WebSocket connection management per audit
- Redis Pub/Sub for multi-worker support
- Automatic cleanup on disconnect
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("sec_scanner.websocket")

# Redis channel prefix for progress updates
PROGRESS_CHANNEL_PREFIX = "scan_progress:"


def get_redis_url() -> str:
    """Get Redis URL from environment."""
    return os.getenv("SEC_SCANNER_REDIS_URL", "redis://localhost:6379/0")


@dataclass
class ProgressUpdate:
    """Progress update message structure."""

    audit_id: str
    step_name: str
    step_status: str  # pending, running, completed, failed
    step_progress: int | None  # 0-100
    message: str | None
    overall_progress: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "progress",
            "audit_id": self.audit_id,
            "step_name": self.step_name,
            "step_status": self.step_status,
            "step_progress": self.step_progress,
            "message": self.message,
            "overall_progress": self.overall_progress,
            "timestamp": self.timestamp,
        }


@dataclass
class ScanComplete:
    """Scan completion message."""

    audit_id: str
    status: str  # completed, failed
    score: int | None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "complete",
            "audit_id": self.audit_id,
            "status": self.status,
            "score": self.score,
            "timestamp": self.timestamp,
        }


class WebSocketManager:
    """Manages WebSocket connections for audit progress updates."""

    def __init__(self):
        # Active WebSocket connections per audit_id
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # Redis pub/sub connection
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        # Background listener task
        self._listener_task: asyncio.Task | None = None
        self._running = False

    async def connect_redis(self) -> None:
        """Initialize Redis connection for Pub/Sub."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                get_redis_url(),
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("WebSocket manager connected to Redis")

    async def disconnect_redis(self) -> None:
        """Close Redis connection."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("WebSocket manager disconnected from Redis")

    async def start_listener(self) -> None:
        """Start background listener for Redis Pub/Sub messages."""
        if self._running:
            return

        await self.connect_redis()

        self._running = True
        self._pubsub = self._redis.pubsub()

        # Subscribe to pattern for all progress channels
        await self._pubsub.psubscribe(f"{PROGRESS_CHANNEL_PREFIX}*")

        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("WebSocket Pub/Sub listener started")

    async def stop_listener(self) -> None:
        """Stop background listener."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        await self.disconnect_redis()
        logger.info("WebSocket Pub/Sub listener stopped")

    async def _listen_loop(self) -> None:
        """Background loop to receive Redis Pub/Sub messages."""
        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "pmessage":
                    # Extract audit_id from channel name
                    channel = message["channel"]
                    if channel.startswith(PROGRESS_CHANNEL_PREFIX):
                        audit_id = channel[len(PROGRESS_CHANNEL_PREFIX) :]
                        data = message["data"]
                        await self._broadcast_to_connections(audit_id, data)
        except asyncio.CancelledError:
            logger.debug("Pub/Sub listener cancelled")
        except Exception as e:
            logger.error(f"Pub/Sub listener error: {e}")

    async def _broadcast_to_connections(self, audit_id: str, data: str) -> None:
        """Broadcast message to all WebSocket connections for an audit."""
        connections = self._connections.get(audit_id, set())
        if not connections:
            return

        # Parse and re-serialize to ensure valid JSON
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in Pub/Sub message for audit {audit_id}")
            return

        dead_connections = set()
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self._connections[audit_id].discard(ws)

    async def connect(self, websocket: WebSocket, audit_id: str) -> None:
        """Accept WebSocket connection and register for audit updates."""
        await websocket.accept()
        self._connections[audit_id].add(websocket)
        logger.info(
            f"WebSocket connected for audit {audit_id}, "
            f"total connections: {len(self._connections[audit_id])}"
        )

    def disconnect(self, websocket: WebSocket, audit_id: str) -> None:
        """Unregister WebSocket connection."""
        self._connections[audit_id].discard(websocket)
        if not self._connections[audit_id]:
            del self._connections[audit_id]
        logger.info(f"WebSocket disconnected for audit {audit_id}")

    def get_connection_count(self, audit_id: str) -> int:
        """Get number of active connections for an audit."""
        return len(self._connections.get(audit_id, set()))


# Global manager instance
manager = WebSocketManager()


# --- Publisher functions (used by workers/service) ---


async def publish_progress_async(update: ProgressUpdate | ScanComplete) -> None:
    """Publish progress update via Redis Pub/Sub (async)."""
    redis_url = get_redis_url()
    redis_client = await aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        channel = f"{PROGRESS_CHANNEL_PREFIX}{update.audit_id}"
        await redis_client.publish(channel, json.dumps(update.to_dict()))
    finally:
        await redis_client.close()


def publish_progress_sync(update: ProgressUpdate | ScanComplete) -> None:
    """Publish progress update via Redis Pub/Sub (sync, for Celery workers)."""
    import redis

    redis_url = get_redis_url()
    redis_client = redis.from_url(redis_url)
    try:
        channel = f"{PROGRESS_CHANNEL_PREFIX}{update.audit_id}"
        redis_client.publish(channel, json.dumps(update.to_dict()))
    finally:
        redis_client.close()


# --- Utility function for service.py ---


def notify_progress(
    audit_id: str,
    step_name: str,
    step_status: str,
    step_progress: int | None = None,
    message: str | None = None,
    overall_progress: int = 0,
) -> None:
    """
    Notify WebSocket clients about progress update.
    This is a sync function safe to call from Celery workers.
    """
    update = ProgressUpdate(
        audit_id=audit_id,
        step_name=step_name,
        step_status=step_status,
        step_progress=step_progress,
        message=message,
        overall_progress=overall_progress,
    )
    try:
        publish_progress_sync(update)
    except Exception as e:
        logger.warning(f"Failed to publish progress update: {e}")


def notify_scan_complete(
    audit_id: str,
    status: str,
    score: int | None = None,
) -> None:
    """
    Notify WebSocket clients that scan is complete.
    This is a sync function safe to call from Celery workers.
    """
    update = ScanComplete(
        audit_id=audit_id,
        status=status,
        score=score,
    )
    try:
        publish_progress_sync(update)
    except Exception as e:
        logger.warning(f"Failed to publish scan complete: {e}")


# --- FastAPI Lifespan helper ---


@asynccontextmanager
async def websocket_lifespan():
    """Context manager for WebSocket manager lifecycle."""
    await manager.start_listener()
    try:
        yield manager
    finally:
        await manager.stop_listener()
