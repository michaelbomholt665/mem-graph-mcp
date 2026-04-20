"""
services/summarizer.py — Async background summarisation worker.

Usage
-----
1. Call ``start_worker()`` from the FastMCP lifespan.
2. Call ``enqueue_summary(conversation_id, transcript)`` from
   ``memory_capture_session`` after persisting messages — this returns
   immediately without blocking the tool response.
3. Call ``stop_worker()`` at shutdown; it drains the queue before exiting.

Retry policy
------------
Up to 3 attempts with exponential backoff (1 s, 2 s, 4 s).
On final failure the Conversation node is updated with a meaningful
status string instead of the previous char-count placeholder.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from functools import partial
from typing import NamedTuple

import ollama

from ..db import db_get_connection, db_update_embedding
from ..embeddings import embeddings_generate
from ..observability import traced_span
from .embed_client import EmbedClientBase

logger = logging.getLogger(__name__)

_SUMMARISE_MODEL = os.getenv("OLLAMA_SUMMARISE_MODEL", "llama3.2")


class Summarizer(EmbedClientBase):
    """Encapsulate summarisation logic with retries and tracing."""

    def __init__(self, model: str = _SUMMARISE_MODEL) -> None:
        super().__init__(model=model)

    async def summarize_transcript(self, transcript: str) -> tuple[str, str]:
        """
        Returns (summary_text, status).
        status is "ok" on success, "failed" on exhausted retries.
        """
        with traced_span("summarizer.summarize_transcript"):
            try:
                summary: str = await self._retry_with_backoff(
                    self._generate_summary, transcript
                )
                return summary, "ok"
            except Exception:  # noqa: BLE001
                return "[summary pending — Ollama unavailable]", "failed"

    async def _generate_summary(self, transcript: str) -> str:
        """Async wrapper for the blocking Ollama call."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._generate_summary_sync, transcript)
        )

    def _generate_summary_sync(self, transcript: str) -> str:
        """Blocking Ollama call — run via run_in_executor."""
        resp = ollama.generate(
            model=self.model or _SUMMARISE_MODEL,
            prompt=(
                "Summarise the following conversation in 2-3 sentences, "
                "focusing on what was accomplished and any key decisions made.\n\n"
                f"{transcript[:8000]}"
            ),
        )
        return resp.response.strip()


_queue: asyncio.Queue[_SummaryJob | None] = asyncio.Queue()
_worker_task: asyncio.Task[None] | None = None


class _SummaryJob(NamedTuple):
    conversation_id: str
    transcript: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enqueue_summary(conversation_id: str, transcript: str) -> None:
    """Non-blocking: add a summarisation job to the background queue."""
    _queue.put_nowait(_SummaryJob(conversation_id, transcript))


def start_worker() -> None:
    """Start the background summarisation worker.  Call once at lifespan start."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_run_worker(), name="summariser-worker")
        logger.info("Summariser worker started.")


async def stop_worker() -> None:
    """
    Signal the worker to drain and stop.  Awaits completion (up to 30 s).
    Call from the FastMCP lifespan shutdown path.
    """
    global _worker_task
    if _worker_task is None:
        return

    try:
        # Drain the queue with a 30 s timeout, then signal sentinel.
        await asyncio.wait_for(_queue.join(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("Summariser worker did not drain within 30 s; cancelling.")
        if _worker_task is not None:
            _worker_task.cancel()
            try:
                await _worker_task
            except (asyncio.CancelledError, Exception):
                pass
        _worker_task = None
        return

    await _queue.put(None)
    try:
        await asyncio.wait_for(_worker_task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("Summariser worker did not stop cleanly; cancelling.")
        _worker_task.cancel()
        try:
            await _worker_task
        except (asyncio.CancelledError, Exception):
            pass

    _worker_task = None
    logger.info("Summariser worker stopped.")


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


async def _run_worker() -> None:
    """Long-running coroutine — processes jobs from the queue until sentinel (None)."""
    summarizer = Summarizer()
    while True:
        job = await _queue.get()
        if job is None:
            _queue.task_done()
            break
        try:
            await _process(job, summarizer)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Summariser worker: unexpected error for conversation %s",
                job.conversation_id,
            )
        finally:
            _queue.task_done()


async def _process(job: _SummaryJob, summarizer: Summarizer) -> None:
    """Attempt to summarise with retries; write result to DB regardless."""
    summary, status = await summarizer.summarize_transcript(job.transcript)
    await _persist_summary(job.conversation_id, summary, status)


async def _persist_summary(
    conversation_id: str,
    summary: str,
    status: str,
) -> None:
    """Write summary + embedding back to the Conversation node."""
    conn = db_get_connection()
    now = datetime.now(timezone.utc)

    # Store summary text and status regardless of embedding success.
    conn.execute(
        """
        MATCH (c:Conversation {id: $id})
        SET c.summary        = $summary,
            c.summary_status = $status,
            c.ended_at       = $ts
        """,
        {"id": conversation_id, "summary": summary, "status": status, "ts": now},
    )

    if status == "ok":
        try:
            vec = await embeddings_generate(summary)
            await db_update_embedding(
                "Conversation", conversation_id, vec, "idx_conv_emb"
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to embeddings_generate summary for conversation %s",
                conversation_id,
            )
