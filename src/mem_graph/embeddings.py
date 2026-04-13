#!/usr/bin/env python3
# src/mem_graph/embeddings.py
"""Async-safe embedding helper with an LRU cache and test shim support.

Refactored to align with Pydantic AI's Embedder interface while preserving
the existing cache, override hook, and dimension guard as the single swap
point for all embedding generation.

Features:
- Provider Shorthand: Uses 'ollama:<model>' for automatic provider detection.
- Interface Split: Specialized embed_query (search) and embed_documents (index).
- Context Safety: Uses truncate=True to handle long documents gracefully.
- LRU Cache: Multi-key cache (text, model, type) to minimize API calls.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from dotenv import load_dotenv
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingSettings
from .config import (
    EMBED_CACHE_SIZE as _CONFIG_EMBED_CACHE_SIZE,
    EMBED_DIM as _CONFIG_EMBED_DIM,
    CODE_EMBED_MODEL as _CONFIG_CODE_MODEL,
    TEXT_EMBED_MODEL as _CONFIG_TEXT_MODEL,
)

load_dotenv()

################
#   CONSTANTS
################

_KNOWN_EMBED_PROVIDERS = (
    "ollama",
    "openai",
    "google-gla",
    "google-vertex",
    "cohere",
    "voyageai",
    "bedrock",
    "sentence-transformers",
)


def _normalise_model_name(model_name: str) -> str:
    """Return a provider-prefixed model name for Pydantic AI."""
    provider, separator, _ = model_name.partition(":")
    if separator and provider in _KNOWN_EMBED_PROVIDERS:
        return model_name
    return f"ollama:{model_name}"


_CODE_MODEL: str = _CONFIG_CODE_MODEL
_TEXT_MODEL: str = _CONFIG_TEXT_MODEL

_CODE_EMBEDDER = Embedder(_normalise_model_name(_CODE_MODEL), defer_model_check=True)
_TEXT_EMBEDDER = Embedder(_normalise_model_name(_TEXT_MODEL), defer_model_check=True)

EMBED_DIM: int = _CONFIG_EMBED_DIM
_CACHE_MAXSIZE: int = _CONFIG_EMBED_CACHE_SIZE

# Context Safety: Set truncate=True in EmbeddingSettings to prevent errors on long docs
_SETTINGS = EmbeddingSettings(truncate=True)

################
#   OVERRIDE HOOK
################

# Test shim: replace this with a deterministic function in conftest.py.
_embed_override: Callable[[str], list[float]] | None = None


################
#   PUBLIC API
################


async def embeddings_generate(text: str) -> list[float]:
    """Return a float embedding vector for the given text."""
    if _embed_override is not None:
        return _validate(_embed_override(text), text)

    return await _cached_embed_async(text, "document")


async def embeddings_code(text: str) -> list[float]:
    """Return a code-aware embedding vector for indexed source content."""
    if _embed_override is not None:
        return _validate(_embed_override(text), text)

    return await _cached_embed_async(text, "code")


async def embeddings_query(text: str) -> list[float]:
    """Return a search-optimised embedding for a query string."""
    if _embed_override is not None:
        return _validate(_embed_override(text), text)

    return await _cached_embed_async(text, "query")


async def embeddings_code_query(text: str) -> list[float]:
    """Return a code-aware query embedding for text-to-code matching."""
    if _embed_override is not None:
        return _validate(_embed_override(text), text)

    return await _cached_embed_async(text, "code_query")


async def embeddings_documents(texts: list[str]) -> list[list[float]]:
    """Return index-optimised embeddings for a list of documents."""
    if _embed_override is not None:
        return [_validate(_embed_override(t), t) for t in texts]

    # Process individually to leverage the cache.
    return [await _cached_embed_async(t, "document") for t in texts]


def embeddings_generate_sync(text: str) -> list[float]:
    """Synchronous wrapper around embeddings_generate() for non-async callers."""
    if _embed_override is not None:
        return _validate(_embed_override(text), text)

    try:
        # Pydantic AI's sync methods are safe to call if no loop is running
        return _cached_embed_sync(text, "document")
    except RuntimeError:
        # Fallback for complex nesting
        return asyncio.run(_cached_embed_async(text, "document"))


def embed_dim() -> int:
    """Return the configured embedding dimension."""
    return EMBED_DIM


################
#   CACHING LAYER
################


async def _cached_embed_async(text: str, input_type: str) -> list[float]:
    """Return a cached embedding for text or generate a new one via Pydantic AI."""
    # Use code embedder for audits/triage/mapping (document), text for others (query/doc)
    is_code = input_type in {"code", "code_query"}
    model_name = _CODE_MODEL if is_code else _TEXT_MODEL
    key_type = input_type
    
    cached = _cache_get(text, model_name, key_type)
    if cached is not None:
        return cached

    embedder = _CODE_EMBEDDER if is_code else _TEXT_EMBEDDER
    if key_type in {"query", "code_query"}:
        result = await embedder.embed_query(text, settings=_SETTINGS)
    else:
        result = await embedder.embed(text, input_type="document", settings=_SETTINGS)

    vec = [float(v) for v in result.embeddings[0]]
    validated = _validate(vec, text)
    _cache_set(text, model_name, key_type, validated)
    return validated


def _cached_embed_sync(text: str, input_type: str) -> list[float]:
    """Return a cached embedding for text or generate a new one via Pydantic AI sync."""
    is_code = input_type in {"code", "code_query"}
    model_name = _CODE_MODEL if is_code else _TEXT_MODEL
    key_type = input_type
    
    cached = _cache_get(text, model_name, key_type)
    if cached is not None:
        return cached

    embedder = _CODE_EMBEDDER if is_code else _TEXT_EMBEDDER
    if key_type in {"query", "code_query"}:
        result = embedder.embed_query_sync(text, settings=_SETTINGS)
    else:
        result = embedder.embed_sync(text, input_type="document", settings=_SETTINGS)

    vec = [float(v) for v in result.embeddings[0]]
    validated = _validate(vec, text)
    _cache_set(text, model_name, key_type, validated)
    return validated


################
#   CACHE STORE
################

# Manual dict-based cache keyed on (text, model, type)
_cache: dict[tuple[str, str, str], list[float]] = {}
_cache_keys: list[tuple[str, str, str]] = []


def _cache_get(text: str, model: str, input_type: str) -> list[float] | None:
    """Return cached vector for (text, model, input_type) or None if not cached."""
    key = (text, model, input_type)
    cached = _cache.get(key)
    if cached is None:
        return None

    if key in _cache_keys:
        _cache_keys.remove(key)
        _cache_keys.append(key)
    return cached


def _cache_set(text: str, model: str, input_type: str, vec: list[float]) -> None:
    """Store vector in cache, evicting the least recently used entry when full."""
    key = (text, model, input_type)
    if key in _cache:
        _cache_keys.remove(key)
    elif len(_cache) >= _CACHE_MAXSIZE:
        oldest = _cache_keys.pop(0)
        _cache.pop(oldest, None)

    _cache[key] = vec
    _cache_keys.append(key)


def clear_cache() -> None:
    """Clear the embedding cache entirely."""
    _cache.clear()
    _cache_keys.clear()


################
#   VALIDATION
################


def _validate(vec: list[float], text: str) -> list[float]:
    """Assert the vector matches the expected EMBED_DIM."""
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"Embedding dim mismatch: got {len(vec)}, expected {EMBED_DIM}. "
            f"Check MEM_GRAPH_EMBED_MODEL and OLLAMA_EMBED_DIM in .env. "
            f"Text snippet: {text[:60]!r}"
        )
    return vec
