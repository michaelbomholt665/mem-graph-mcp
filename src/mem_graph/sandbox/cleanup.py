"""Periodic stale sandbox cleanup task."""

from __future__ import annotations

import logging

import anyio

from .manager import SessionSandboxManager

logger = logging.getLogger(__name__)


async def run_periodic_cleanup(manager: SessionSandboxManager) -> None:
    """Run best-effort cleanup of expired sandbox sessions until cancelled."""

    if not manager.enabled:
        return
    interval = manager.settings.cleanup_interval_seconds
    while True:
        cleaned = await manager.cleanup_stale()
        if cleaned:
            logger.info("sandbox_stale_cleanup sessions=%s", ",".join(cleaned))
        await anyio.sleep(interval)
