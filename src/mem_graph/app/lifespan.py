"""Server lifespan and background service wiring."""

from __future__ import annotations

import logging
import os
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
from .constants import (
    BANNER_BOX_TEMPLATE,
    BANNER_LOGO,
    HOST,
    OPENAPI_SPECS,
    PORT,
    SERVER_VERSION,
    TRANSPORT,
)
from ..config import CODE_EMBED_MODEL, TEXT_EMBED_MODEL
from .tools import catalog_tools

logger = logging.getLogger(__name__)


def build_lifespan(mcp: FastMCP):
    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:  # noqa: ARG001
        if sys.stderr.isatty():
            # 1. Status detection
            try:
                import tree_sitter  # noqa: F401
                ts_status = "Ready"
            except ImportError:
                ts_status = "Unavailable"

            ag_ui_status = "Ready"
            sandbox_status = "Unavailable (Coming soon)"
            lakehouse_status = "Available" if os.getenv("LAKEHOUSE_URL") else "Unavailable"

            # 2. Extract counts and info
            tool_count = len(await catalog_tools(mcp))
            prompt_count = len(await mcp.list_prompts())
            # Skills are providers in FastMCP 
            skills_count = len(mcp.providers) 
            
            # Clean model names for display
            text_model = TEXT_EMBED_MODEL.split("/")[-1] if TEXT_EMBED_MODEL else "Default"
            code_model = CODE_EMBED_MODEL.split("/")[-1] if CODE_EMBED_MODEL else "Default"

            # 3. Format lines for the banner box
            status_lines = [
                f"  | Dashboard:  http://{HOST}:{PORT}/dashboard".ljust(91) + "|",
                "  | Logfire:    https://logfire-eu.pydantic.dev/michaelbomholt/memgraph".ljust(91) + "|",
                f"  | Link:       http://{HOST}:{PORT}/mcp".ljust(91) + "|",
                "  | ".ljust(91) + "|",
                f"  | Tree-sitter parsers {ts_status}".ljust(91) + "|",
                f"  | AG-UI {ag_ui_status}".ljust(91) + "|",
                f"  | Sandbox {sandbox_status}".ljust(91) + "|",
                f"  | Lakehouse {lakehouse_status}".ljust(91) + "|",
                "  | ".ljust(91) + "|",
                f"  | Embedding text model: {text_model}".ljust(91) + "|",
                f"  | Embedding code model: {code_model}".ljust(91) + "|",
                "  | ".ljust(91) + "|",
                f"  | Tools: {tool_count} | Prompts: {prompt_count} | Skills: {skills_count} | Version: {SERVER_VERSION}".ljust(91) + "|",
                f"  | Discovery: BM25 search | Transport: {TRANSPORT.upper()}".ljust(91) + "|",
            ]

            print(BANNER_LOGO, file=sys.stderr)
            print(BANNER_BOX_TEMPLATE.format(lines="\n".join(status_lines)), file=sys.stderr)
            print(
                f"  Version: {SERVER_VERSION} | Discovery: BM25 search | Host: {HOST}:{PORT}\n",
                file=sys.stderr,
            )

        await to_thread.run_sync(db_init_engine)
        start_worker()
        await task_queue.startup()
        await _load_openapi_providers(mcp)
        
        # Minimised summary log exactly as requested to be below logo
        logger.info(
            "Starting server 'syntx-memory' v%s (HTTP/SSE/Health) on %s:%s",
            SERVER_VERSION, HOST, PORT
        )
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
