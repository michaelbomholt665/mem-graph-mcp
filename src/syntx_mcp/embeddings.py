"""
embeddings.py — Async-safe Ollama embedding helper.

``embed(text)`` is the only public function tools need.
It offloads the blocking Ollama SDK call to a thread-pool executor so it
doesn't stall the FastMCP event loop.
"""

from __future__ import annotations

import asyncio
import os
from functools import partial

import ollama
from dotenv import load_dotenv

load_dotenv()

_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
_DIM = int(os.getenv("OLLAMA_EMBED_DIM", "768"))
_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30s")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def embed(text: str) -> list[float]:
    """Async-safe embed — offloads blocking Ollama call to thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_embed_sync, text))


def embed_dim() -> int:
    """Return the configured embedding dimension."""
    return _DIM


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _embed_sync(text: str) -> list[float]:
    """Blocking Ollama call.  Do NOT call directly from async code."""
    response = ollama.embed(model=_MODEL, input=text, keep_alive=_KEEP_ALIVE)
    vec = list(response.embeddings[0])
    if len(vec) != _DIM:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vec)}, expected {_DIM}. "
            f"Check OLLAMA_EMBED_MODEL and OLLAMA_EMBED_DIM in .env"
        )
    return vec
