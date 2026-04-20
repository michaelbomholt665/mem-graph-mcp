"""
resources/prompts_evals.py — Eval-specific prompt variations for scorer calibration.

These variants are used by the eval framework to test the robustness of the
prompt system. They are NOT used in production runs.
"""

from __future__ import annotations

from .prompts import PROMPT_REGISTRY

################
#   EVAL FIXTURES
################

# Minimal persona prompt variant for fast eval runs (strips domain knowledge)
EVAL_MINIMAL_PERSONA = "You are a code analysis agent. Be precise and concise."

# ReAct-Challenge variant with reduced step count for eval speed
EVAL_REACT_CHALLENGE_SHORT = """Use the ReAct-Challenge pattern (abbreviated for eval):
1. **Plan**: State your approach in one sentence.
2. **Challenge**: Name one risk or missing context.
3. **Execute**: Proceed if the challenge is acceptable."""

# COT variant with fixed N=2 paths for deterministic eval scoring
EVAL_COT_TWO_PATHS = """Use Chain-of-Thought with exactly 2 candidate paths:
1. State Path A and Path B.
2. Evaluate which is stronger.
3. Proceed with the stronger path."""

# Registry of eval-specific variants (keyed separately to avoid production overlap)
EVAL_PROMPT_REGISTRY: dict[str, str] = {
    "eval.minimal_persona": EVAL_MINIMAL_PERSONA,
    "eval.react_challenge.short": EVAL_REACT_CHALLENGE_SHORT,
    "eval.cot.two_paths": EVAL_COT_TWO_PATHS,
    # Mirror all production stage prompts for regression evals
    **{f"eval.{k}": v for k, v in PROMPT_REGISTRY.items() if k.startswith("stage.")},
}


def get_eval_prompt(key: str) -> str:
    """
    Return an eval-specific prompt variant by key.

    Falls back to the production PROMPT_REGISTRY if the key does not exist
    in the eval-specific registry.

    Args:
        key: Eval prompt key, e.g. 'eval.react_challenge.short'.

    Returns:
        Prompt string, or empty string if not found in either registry.
    """
    return EVAL_PROMPT_REGISTRY.get(key, PROMPT_REGISTRY.get(key, ""))
