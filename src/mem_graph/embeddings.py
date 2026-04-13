#!/usr/bin/env python3
# src/mem_graph/embeddings.py
"""
Async-safe embedding helper with LRU cache and test shim support.

Wraps Ollama's embedding API in a pydantic-ai-compatible interface.
When pydantic-ai ships native EmbeddingsModel support this module is
the single swap point — callers use embed() and embed_sync() throughout.

embed(text)      — primary async API, used by all tools and agents.
embed_sync(text) — thin sync wrapper for callers that cannot be async.
EMBED_DIM        — authoritative dimension constant, read by db.py and
                   SchemaMeta validation at startup.
"""

from __future__ import annotations

################
#   IMPORTS
################

import asyncio
import os
from functools import partial
from typing import Callable

import ollama
from dotenv import load_dotenv

from .config import (
    EMBED_CACHE_SIZE as _CONFIG_EMBED_CACHE_SIZE,
    EMBED_DIM as _CONFIG_EMBED_DIM,
    EMBED_MODEL as _CONFIG_EMBED_MODEL,
)

load_dotenv()

################
#   CONSTANTS
################

_MODEL: str = _CONFIG_EMBED_MODEL
EMBED_DIM: int = _CONFIG_EMBED_DIM
_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30s")
_CACHE_MAXSIZE: int = _CONFIG_EMBED_CACHE_SIZE

################
#   OVERRIDE HOOK
################

# Test shim: replace this with a deterministic function in conftest.py:
#   import mem_graph.embeddings as emb
#   emb._embed_override = lambda text: [0.0] * emb.EMBED_DIM
_embed_override: Callable[[str], list[float]] | None = None


################
#   PUBLIC API
################


async def embed(text: str) -> list[float]:
    """
    Return a float embedding vector for the given text.

    Uses the override shim if set (for tests), otherwise calls Ollama
    via a thread-pool executor to avoid blocking the async event loop.
    Validates the returned vector dimension before returning.
    """
    if _embed_override is not None:
        vec = _embed_override(text)
        return _validate(vec, text)

    vec = await _cached_embed_async(text)
    return vec


def embed_sync(text: str) -> list[float]:
    """
    Synchronous wrapper around embed() for non-async callers.

    Runs the async embed in a new event loop. Do not call from within
    a running event loop — use await embed() there instead.
    """
    if _embed_override is not None:
        vec = _embed_override(text)
        return _validate(vec, text)

    return asyncio.run(_cached_embed_async(text))


def embed_dim() -> int:
    """Return the configured embedding dimension (alias for EMBED_DIM)."""
    return EMBED_DIM


################
#   CACHING LAYER
################


async def _cached_embed_async(text: str) -> list[float]:
    """
    Async embed with LRU cache keyed by (text, model).

    Cache is keyed on both text and model so a model change at runtime
    does not serve stale vectors from a previous model.
    The underlying sync call is offloaded to a thread-pool executor.
    """
    cached = _cache_get(text, _MODEL)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    vec = await loop.run_in_executor(None, partial(_embed_sync_raw, text))
    validated = _validate(vec, text)
    _cache_set(text, _MODEL, validated)
    return validated


################
#   CACHE STORE
################

# Manual dict-based cache so we can key on (text, model) and keep a tiny
# LRU ordering without pulling in extra dependencies.
_cache: dict[tuple[str, str], list[float]] = {}
_cache_keys: list[tuple[str, str]] = []


def _cache_get(text: str, model: str) -> list[float] | None:
    """Return cached vector for (text, model) or None if not cached."""
    key = (text, model)
    cached = _cache.get(key)
    if cached is None:
        return None

    if key in _cache_keys:
        _cache_keys.remove(key)
        _cache_keys.append(key)
    return cached


def _cache_set(text: str, model: str, vec: list[float]) -> None:
    """
    Store vector in cache, evicting the least recently used entry when full.
    """
    key = (text, model)
    if key in _cache:
        _cache_keys.remove(key)
    elif len(_cache) >= _CACHE_MAXSIZE:
        oldest = _cache_keys.pop(0)
        _cache.pop(oldest, None)

    _cache[key] = vec
    _cache_keys.append(key)


def clear_cache() -> None:
    """
    Clear the embedding cache entirely.

    Useful in tests and after a model change to prevent stale vectors.
    """
    _cache.clear()
    _cache_keys.clear()


################
#   OLLAMA BACKEND
################


def _embed_sync_raw(text: str) -> list[float]:
    """
    Blocking Ollama embed call.

    Do NOT call directly from async code — use embed() instead.
    Separated from the public API so the cache layer can wrap it
    without also wrapping the validation step.
    """
    response = ollama.embed(model=_MODEL, input=text, keep_alive=_KEEP_ALIVE)
    return list(response.embeddings[0])


################
#   VALIDATION
################


def _validate(vec: list[float], text: str) -> list[float]:
    """
    Assert the vector matches the expected EMBED_DIM.

    Raises ValueError with a clear message if the dimension is wrong
    so misconfiguration is caught at embed time, not at DB write time.
    """
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vec)}, expected {EMBED_DIM}. "
            f"Check MEM_GRAPH_EMBED_MODEL and OLLAMA_EMBED_DIM in .env. "
            f"Text snippet: {text[:60]!r}"
        )
    return vec