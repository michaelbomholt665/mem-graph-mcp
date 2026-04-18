"""Server lifespan and background service wiring."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from anyio import to_thread
from fastmcp import FastMCP

from ..db import db_close_engine, db_init_engine
from ..observability.logfire_setup import shutdown_logfire
from ..observability.otel_setup import shutdown_observability
from ..providers.openapi import build_openapi_provider
from ..services.summarizer import start_worker, stop_worker
from ..services.task_queue import task_queue
from .constants import BANNER, HOST, OPENAPI_SPECS, PORT, SERVER_VERSION

logger = logging.getLogger(__name__)


def build_lifespan(mcp: FastMCP):
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
        if sys.stderr.isatty():
            print(BANNER, file=sys.stderr)
            print(
                f"  Version: {SERVER_VERSION} | CodeMode: ENABLED | Host: {HOST}:{PORT}\n",
                file=sys.stderr,
            )

        await to_thread.run_sync(db_init_engine)
        start_worker()
        await task_queue.startup()
        await _load_openapi_providers(mcp)
        logger.info("mem-graph server ready.")
        yield
        pending = await task_queue.shutdown()
        if pending["queued_cancelled"] or pending["running_cancelled"]:
            logger.warning(
                "background task queue cleared on shutdown queued=%s running=%s",
                pending["queued_cancelled"],
                pending["running_cancelled"],
            )
        await stop_worker()
        await to_thread.run_sync(db_close_engine)
        shutdown_observability()
        shutdown_logfire()
        logger.info("mem-graph server shut down cleanly.")

    return lifespan


async def _load_openapi_providers(mcp: FastMCP) -> None:
    for spec_url in OPENAPI_SPECS:
        try:
            provider = await build_openapi_provider(spec_url)
            mcp.add_provider(provider)
            logger.info("openapi_provider_loaded spec=%s", spec_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("openapi_provider_failed spec=%s error=%s", spec_url, exc)

