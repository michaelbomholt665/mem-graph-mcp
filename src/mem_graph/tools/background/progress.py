from __future__ import annotations

from typing import Protocol

from fastmcp.server.context import Context


class ProgressReporter(Protocol):
    """Protocol implemented by task progress sinks."""

    async def update(
        self,
        current: int,
        total: int,
        current_step: str,
        status_text: str,
    ) -> None: ...


def format_progress_message(current_step: str, status_text: str) -> str:
    step = current_step.strip() or "working"
    detail = status_text.strip() or "Working."
    return f"{step}: {detail}"


class ContextProgressReporter:
    """Progress reporter that emits FastMCP progress notifications."""

    def __init__(self, ctx: Context | None) -> None:
        self._ctx = ctx

    async def update(
        self,
        current: int,
        total: int,
        current_step: str,
        status_text: str,
    ) -> None:
        if self._ctx is None:
            return

        message = format_progress_message(current_step, status_text)
        await self._ctx.info(message)
        await self._ctx.report_progress(current, total, message)


async def report_step(
    reporter: ProgressReporter,
    current: int,
    total: int,
    current_step: str,
    status_text: str,
) -> None:
    """Emit a normalized progress update."""

    await reporter.update(current, total, current_step, status_text)