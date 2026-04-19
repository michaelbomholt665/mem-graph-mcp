#!/usr/bin/env python3
# src/mem_graph/resources/workflows/reasoning.py
"""Typed reasoning policies: ReAct self-challenge and bounded Tree-of-Thought."""

from __future__ import annotations

from .models import ReasoningMode, ReasoningPolicy

################
#   REACT CHALLENGE POLICY
################

REACT_CHALLENGE_POLICY = ReasoningPolicy(
    mode=ReasoningMode.REACT_CHALLENGE,
    description=(
        "ReAct with mandatory self-challenge step. "
        "Required before every final action choice."
    ),
    required_steps=[
        "observe: Review all available context and known state.",
        "draft: Form an initial action or hypothesis.",
        "challenge: Ask what could be wrong with the draft. "
        "Check for missing evidence. Evaluate at least one alternative approach.",
        "decide: Make the final choice informed by the challenge step and execute.",
    ],
)

################
#   BOUNDED TREE-OF-THOUGHT POLICY
################

BOUNDED_TOT_POLICY = ReasoningPolicy(
    mode=ReasoningMode.BOUNDED_TOT,
    description=(
        "Bounded Tree-of-Thought for high-ambiguity tasks. "
        "Small width/depth only with explicit pruning criteria and budget caps."
    ),
    required_steps=[
        "observe: Review all available context and known state.",
        "branch: Generate a small set of candidate approaches (width ≤ tree_width).",
        "evaluate: Score each branch against the pruning criteria.",
        "prune: Eliminate branches that fail any pruning criterion.",
        "expand: Expand the highest-scoring branch to at most tree_depth levels.",
        "decide: Select the best surviving path and execute.",
    ],
    tree_width=3,
    tree_depth=2,
    pruning_criteria=[
        "Violates an active architectural decision.",
        "Requires more context than is available.",
        "Exceeds the tool budget for the current stage.",
        "Creates a circular dependency.",
    ],
    budget_cap=500,
)

################
#   POLICY MAP
################

REASONING_POLICY_MAP: dict[ReasoningMode, ReasoningPolicy] = {
    ReasoningMode.REACT_CHALLENGE: REACT_CHALLENGE_POLICY,
    ReasoningMode.BOUNDED_TOT: BOUNDED_TOT_POLICY,
}


def get_reasoning_policy(mode: ReasoningMode) -> ReasoningPolicy:
    """Return the ReasoningPolicy for the given mode."""
    return REASONING_POLICY_MAP[mode]


def reasoning_policy_prompt(policy: ReasoningPolicy) -> str:
    """Render the reasoning policy as a structured prompt block.

    Produces a string suitable for injection into an agent system prompt
    to enforce deterministic step-by-step reasoning.
    """
    lines = [
        f"## Reasoning Policy: {policy.mode.value}",
        "",
        policy.description,
        "",
        "### Required Steps (in order)",
    ]
    for i, step in enumerate(policy.required_steps, 1):
        lines.append(f"{i}. {step}")

    if policy.mode == ReasoningMode.BOUNDED_TOT:
        lines.extend(
            [
                "",
                "### ToT Constraints",
                f"- Width: {policy.tree_width} branches maximum",
                f"- Depth: {policy.tree_depth} levels maximum",
                f"- Budget cap: {policy.budget_cap} reasoning steps",
                "",
                "### Pruning Criteria",
            ]
        )
        for criterion in policy.pruning_criteria:
            lines.append(f"- {criterion}")

    lines.extend(
        [
            "",
            "Do not skip or reorder steps. "
            "Self-challenge is not free-form reflection — it is a deterministic gate.",
        ]
    )
    return "\n".join(lines)
