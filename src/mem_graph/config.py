#!/usr/bin/env python3
# src/mem_graph/config.py
"""
Central configuration for mem-graph agents and embeddings.

Single source of truth for model identifiers, tier definitions, and
feature flags. All agents import from here rather than reading env vars
directly, so a model change requires touching one file or one env var.
"""

from __future__ import annotations

import os
from enum import Enum

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


def config_model_settings(*, temperature: float, top_p: float) -> ModelSettings:
    """Return typed model settings supported by the current agent model APIs."""
    settings: ModelSettings = {"temperature": temperature, "top_p": top_p}
    return settings


################
#   MODEL TIERS
################


class ModelTier(str, Enum):
    """
    Four-tier dynamic model selection strategy.

    Tiers are chosen by the Router Agent based on task complexity.
    Higher tiers provide more intelligence at greater token cost.
    """

    AUTOPILOT = "autopilot"  # XHigh — large refactors, 10–30 edits, deep debugging
    STANDARD = "standard"    # Medium — multi-file audits, standard decomposition
    MICRO = "micro"          # Mini — single-file edits, typo fixes, simple queries
    TURBO = "turbo"          # Fast — high-volume classification, pattern matching


#: Maps each tier alias to its concrete model identifier.
MODEL_TIER_MAP: dict[str, str] = {
    ModelTier.AUTOPILOT: os.getenv("MEM_GRAPH_MODEL_AUTOPILOT", "openai:gpt-5.4-xhigh"),
    ModelTier.STANDARD: os.getenv("MEM_GRAPH_MODEL_STANDARD", "openai:gpt-5.4-medium"),
    ModelTier.MICRO: os.getenv("MEM_GRAPH_MODEL_MICRO", "openai:gpt-5.4-mini"),
    ModelTier.TURBO: os.getenv("MEM_GRAPH_MODEL_TURBO", "x-ai/grok-code-fast-1:optimized:free"),
}

# Concurrency scaling thresholds (file count → worker count)
_SCALE_THRESHOLD_MED: int = 10   # ≥10 files → 2 workers
_SCALE_THRESHOLD_MAX: int = 50   # ≥50 files → 3 workers
_SCALE_SOLO_THRESHOLD: int = 30  # ≥30+complex → Solo Mode (Autopilot, no batching)


def config_get_model_for_tier(tier: str | ModelTier) -> str:
    """
    Resolve a tier alias to its concrete model identifier.

    Falls back to AGENT_MODEL if the tier is not found in MODEL_TIER_MAP,
    ensuring agents always receive a valid model string.

    Args:
        tier: A ModelTier enum value or its string alias.

    Returns:
        The model identifier string for this tier.
    """
    return MODEL_TIER_MAP.get(ModelTier(tier) if isinstance(tier, str) else tier, AGENT_MODEL)


def config_get_concurrency_for_files(file_count: int) -> int:
    """
    Return the appropriate worker count for a given file corpus size.

    Implements the 3-tier scaling rule:
    - <10 files → 1 worker (sequential)
    - 10–50 files → 2 workers (parallel batches)
    - >50 files → 3 workers (max concurrency)

    Args:
        file_count: Total number of files to process.

    Returns:
        Number of concurrent workers to use.
    """
    if file_count >= _SCALE_THRESHOLD_MAX:
        return 3
    if file_count >= _SCALE_THRESHOLD_MED:
        return 2
    return 1


def config_is_solo_mode(file_count: int, *, high_complexity: bool) -> bool:
    """
    Determine whether a task should run in Solo Mode (no batching).

    Solo Mode uses the Autopilot tier on the full context without batching.
    Triggered only when the task is both large and flagged as high-complexity.

    Args:
        file_count: Total number of files to process.
        high_complexity: Whether the Router flagged this task as Autopilot tier.

    Returns:
        True if Solo Mode should be used.
    """
    return high_complexity and file_count <= _SCALE_SOLO_THRESHOLD


################
#   EMBED CONFIG
################

CODE_EMBED_MODEL: str = os.getenv(
    "OLLAMA_CODE_EMBED_MODEL", "hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M"
)
TEXT_EMBED_MODEL: str = os.getenv(
    "OLLAMA_TEXT_EMBED_MODEL", "hf.co/nomic-ai/nomic-embed-text-v1.5-GGUF:F16"
)
EMBED_DIM: int = int(os.getenv("OLLAMA_EMBED_DIM", "768"))
EMBED_CACHE_SIZE: int = int(os.getenv("MEM_GRAPH_EMBED_CACHE_SIZE", "512"))

# Ollama-specific keep_alive durations (e.g. "20m" or "2m")
# Short timeout for the large code model to free VRAM quickly.
OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "20m")
OLLAMA_CODE_KEEP_ALIVE: str = os.getenv("OLLAMA_CODE_KEEP_ALIVE", "2m")

JINA_URL: str = os.getenv("JINA_URL", "").rstrip("/")
JINA_USERNAME: str = os.getenv("JINA_USERNAME", "")
JINA_TOKEN: str = os.getenv("JINA_TOKEN", "")
JINA_PROJECT_KEY: str = os.getenv("JINA_PROJECT_KEY", "")
JINA_MATCH_THRESHOLD: float = float(os.getenv("JINA_MATCH_THRESHOLD", "0.72"))
JINA_MAX_RESULTS: int = int(os.getenv("JINA_MAX_RESULTS", "25"))
JINA_EMBEDDER_TTL_SECONDS: int = int(os.getenv("JINA_EMBEDDER_TTL_SECONDS", "300"))
FILE_TREE_DEFAULT_ROOT: str = os.getenv("MEM_GRAPH_FILE_TREE_ROOT", "")


# Feature flags for runtime path selection
# When True, prefer FastMCP native task and confirmation features (if available)
FASTMCP_USE_NATIVE_TASKS: bool = os.getenv("FASTMCP_USE_NATIVE_TASKS", "false").lower() == "true"
FASTMCP_ENABLE_CONFIRMATIONS: bool = os.getenv("FASTMCP_ENABLE_CONFIRMATIONS", "true").lower() == "true"
