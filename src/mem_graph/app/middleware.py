"""FastMCP middleware."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastmcp.server.middleware.middleware import CallNext, Middleware, MiddlewareContext

logger = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    """Log MCP tool calls and elapsed time."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        tool_name: str = getattr(context.message, "name", "<unknown>")
        start = time.monotonic()
        try:
            result = await call_next(context)
            elapsed = (time.monotonic() - start) * 1000
            logger.info("tool_call tool=%s elapsed_ms=%.1f", tool_name, elapsed)
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "tool_error tool=%s elapsed_ms=%.1f error=%s",
                tool_name,
                elapsed,
                exc,
            )
            raise

