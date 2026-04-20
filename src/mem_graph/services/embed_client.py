#!/usr/bin/env python3
# src/mem_graph/services/embed_client.py
"""
EmbedClientBase — Shared retry logic for embedding and external API clients.

Centralises exponential backoff patterns to ensure robust interactions
with Ollama, Jina, and other external services.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


class EmbedClientBase:
    """
    Base class for services requiring robust retry logic with backoff.

    Used by TextEmbedService (Jina issues), JinaEmbedder, and Summarizer.
    """

    def __init__(
        self,
        model: str | None = None,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        """
        Initialise retry configuration.

        Args:
            model: Optional model name for logging context.
            max_retries: Maximum number of attempts.
            backoff_factor: Multiplier for exponential backoff (2^attempt).
        """
        self.model = model
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    async def _retry_with_backoff(
        self,
        fn: Callable[..., T] | Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute a function with exponential backoff retries.

        Args:
            fn: The async function to execute.
            *args: Positional arguments for fn.
            **kwargs: Keyword arguments for fn.

        Returns:
            The result of the successful function call.

        Raises:
            The last exception encountered after exhausting all retries.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Support both async and sync functions (wrapped in executor if needed)
                # But here we assume fn is either async or properly wrapped.
                if inspect.iscoroutinefunction(fn):
                    return await cast(Awaitable[T], fn(*args, **kwargs))
                return cast(T, fn(*args, **kwargs))
            except Exception as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    logger.error(
                        "Retry limit reached for %s (model=%s): %s",
                        fn.__name__,
                        self.model,
                        exc,
                    )
                    break

                wait_time = self.backoff_factor ** (attempt - 1)
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                    attempt,
                    self.max_retries,
                    fn.__name__,
                    exc,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        if last_exc:
            raise last_exc
        raise RuntimeError("Retry loop exited without result or exception")
