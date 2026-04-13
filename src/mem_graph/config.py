#!/usr/bin/env python3
# src/mem_graph/config.py
"""
Central configuration for mem-graph agents and embeddings.

Single source of truth for model identifiers and feature flags.
All agents import from here rather than reading env vars directly,
so a model change requires touching one file or one env var.
"""

from __future__ import annotations

import os

from pydantic_ai.settings import ModelSettings

################
#   AGENT CONFIG
################

AGENT_MODEL: str = os.getenv("MEM_GRAPH_AGENT_MODEL") or (
    "openai:gpt-5-mini"
    if os.getenv("OPENAI_API_KEY")
    else "x-ai/grok-code-fast-1:optimized:free"
)

# Prevents import-time provider validation failures in test environments.
# Keep True — tests override via agent.override(model=TestModel()).
DEFER_AGENT_MODEL_CHECK: bool = True


def build_model_settings(*, temperature: float, top_p: float) -> ModelSettings:
    """Return typed model settings supported by the current agent model APIs."""
    settings: ModelSettings = {"temperature": temperature, "top_p": top_p}
    return settings


################
#   EMBED CONFIG
################

EMBED_MODEL: str = os.getenv(
    "MEM_GRAPH_EMBED_MODEL",
    os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
)
EMBED_DIM: int = int(os.getenv("OLLAMA_EMBED_DIM", "1536"))
EMBED_CACHE_SIZE: int = int(os.getenv("MEM_GRAPH_EMBED_CACHE_SIZE", "512"))
