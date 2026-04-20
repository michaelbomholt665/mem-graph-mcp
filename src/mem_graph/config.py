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
from typing import Literal

from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

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


def config_build_usage_limits(
    *,
    request_limit: int = 50,
    tool_calls_limit: int | None = None,
    input_tokens_limit: int | None = None,
    output_tokens_limit: int | None = None,
    total_tokens_limit: int | None = None,
) -> UsageLimits:
    """Build a consistent UsageLimits object for bounded agent runs."""
    return UsageLimits(
        request_limit=request_limit,
        tool_calls_limit=tool_calls_limit,
        input_tokens_limit=input_tokens_limit,
        output_tokens_limit=output_tokens_limit,
        total_tokens_limit=total_tokens_limit,
    )


def config_build_orchestrator_usage_limits(total_batches: int) -> UsageLimits:
    """Return a conservative usage budget for batched orchestration jobs."""
    bounded_batches = max(1, total_batches)
    return config_build_usage_limits(
        request_limit=(bounded_batches * 2) + 4,
        tool_calls_limit=(bounded_batches * 2) + 2,
    )


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
    STANDARD = "standard"  # Medium — multi-file audits, standard decomposition
    MICRO = "micro"  # Mini — single-file edits, typo fixes, simple queries
    TURBO = "turbo"  # Fast — high-volume classification, pattern matching


GPT_5_4_XHIGH = "openai:gpt-5.4-xhigh"
GPT_5_4_MINI = "openai:gpt-5.4-mini"

#: Maps each tier alias to its concrete model identifier.
MODEL_TIER_MAP: dict[str, str] = {
    ModelTier.AUTOPILOT: os.getenv("MEM_GRAPH_MODEL_AUTOPILOT", GPT_5_4_XHIGH),
    ModelTier.STANDARD: os.getenv("MEM_GRAPH_MODEL_STANDARD", "openai:gpt-5.4-medium"),
    ModelTier.MICRO: os.getenv("MEM_GRAPH_MODEL_MICRO", GPT_5_4_MINI),
    ModelTier.TURBO: os.getenv(
        "MEM_GRAPH_MODEL_TURBO", "x-ai/grok-code-fast-1:optimized:free"
    ),
}


WorkflowStageName = Literal[
    "context_gather",
    "planning",
    "implementation",
    "audit",
    "debug_validation",
    "documentation",
    "context_map_update",
    "memory_bank_sync",
]

WORKFLOW_STAGE_MODEL_MAP: dict[WorkflowStageName, str] = {
    "context_gather": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_CONTEXT", GPT_5_4_MINI),
    "planning": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_PLANNING", GPT_5_4_MINI),
    "implementation": os.getenv(
        "MEM_GRAPH_WORKFLOW_MODEL_IMPLEMENTATION", GPT_5_4_XHIGH
    ),
    "audit": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_AUDIT", GPT_5_4_XHIGH),
    "debug_validation": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_DEBUG", GPT_5_4_XHIGH),
    "documentation": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_DOCUMENTATION", GPT_5_4_MINI),
    "context_map_update": os.getenv(
        "MEM_GRAPH_WORKFLOW_MODEL_CONTEXT_MAP", GPT_5_4_MINI
    ),
    "memory_bank_sync": os.getenv("MEM_GRAPH_WORKFLOW_MODEL_MEMORY_BANK", GPT_5_4_MINI),
}


def config_get_model_for_workflow_stage(
    stage: WorkflowStageName,
    overrides: dict[str, str] | None = None,
) -> str:
    """
    Resolve the model for a workflow stage with optional caller overrides.

    Coding, audit, and debugging stages default to stronger models while
    context, documentation, and memory stages default to cheaper mini models.
    """
    model = WORKFLOW_STAGE_MODEL_MAP[stage]
    if overrides and stage in overrides:
        model = overrides[stage]
    return _normalize_model_name(model)


def _normalize_model_name(model: str) -> str:
    """
    Normalize model strings for Pydantic AI provider inference.

    Maps common aliases or proxy prefixes (like 'x-ai/') to their
    canonical Pydantic AI equivalents (like 'xai:').
    """
    if model.startswith("x-ai/"):
        return model.replace("x-ai/", "xai:", 1)
    return model


# Concurrency scaling thresholds (file count → worker count)
_SCALE_THRESHOLD_MED: int = 10  # ≥10 files → 2 workers
_SCALE_THRESHOLD_MAX: int = 50  # ≥50 files → 3 workers
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
    model = MODEL_TIER_MAP.get(
        ModelTier(tier) if isinstance(tier, str) else tier, AGENT_MODEL
    )
    return _normalize_model_name(model)


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
TEXT_EMBED_DIM: int = int(
    os.getenv("OLLAMA_TEXT_EMBED_DIM", os.getenv("OLLAMA_EMBED_DIM", "768"))
)
CODE_EMBED_DIM: int = int(os.getenv("OLLAMA_CODE_EMBED_DIM", "2048"))
EMBED_DIM: int = TEXT_EMBED_DIM
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
FASTMCP_USE_NATIVE_TASKS: bool = (
    os.getenv("FASTMCP_USE_NATIVE_TASKS", "false").lower() == "true"
)
FASTMCP_ENABLE_CONFIRMATIONS: bool = (
    os.getenv("FASTMCP_ENABLE_CONFIRMATIONS", "true").lower() == "true"
)
