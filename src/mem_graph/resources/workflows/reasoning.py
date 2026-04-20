#!/usr/bin/env python3
# src/mem_graph/resources/workflows/reasoning.py
"""Typed reasoning policies: ReAct self-challenge, REACT_2, bounded Tree-of-Thought, and CoT."""

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
#   REACT_2 POLICY
################

REACT_2_POLICY = ReasoningPolicy(
    mode=ReasoningMode.REACT_2,
    description=(
        "ReAct iteration policy for refining prior work. "
        "Used when an earlier version of the output already exists "
        "and the agent must decide whether to confirm, improve, or drop it."
    ),
    required_steps=[
        "observe: Review the prior output and the current objective.",
        "plan: Draft a minimal change set to address outstanding gaps.",
        "evaluate: For each planned change decide: confirm (keep as-is), "
        "improve (needs adjustment), or drop (no longer relevant).",
        "execute: Apply only confirmed and improved items.",
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
#   CHAIN-OF-THOUGHT POLICY
################

COT_POLICY = ReasoningPolicy(
    mode=ReasoningMode.COT,
    description=(
        "Chain-of-Thought for multi-step reasoning where each step reframes the next. "
        "Runs N parallel paths per step and carries the best-scoring path forward."
    ),
    required_steps=[
        "decompose: Break the objective into an ordered sequence of reasoning steps.",
        "generate: For each step, produce at least two candidate continuations.",
        "score: Rank continuations by correctness, completeness, and consistency.",
        "carry: Select the top-scoring continuation and use it as the input to the next step.",
        "conclude: Synthesize the final answer from the last carried step.",
    ],
    tree_width=2,
    tree_depth=4,
    budget_cap=300,
)

################
#   POLICY MAP
################

REASONING_POLICY_MAP: dict[ReasoningMode, ReasoningPolicy] = {
    ReasoningMode.REACT_CHALLENGE: REACT_CHALLENGE_POLICY,
    ReasoningMode.REACT_2: REACT_2_POLICY,
    ReasoningMode.BOUNDED_TOT: BOUNDED_TOT_POLICY,
    ReasoningMode.COT: COT_POLICY,
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

    if policy.mode == ReasoningMode.COT:
        lines.extend(
            [
                "",
                "### Chain Constraints",
                f"- Candidates per step: {policy.tree_width} minimum",
                f"- Max chain depth: {policy.tree_depth} steps",
                f"- Budget cap: {policy.budget_cap} reasoning tokens",
            ]
        )

    lines.extend(
        [
            "",
            "Do not skip or reorder steps. "
            "Self-challenge is not free-form reflection — it is a deterministic gate.",
        ]
    )
    return "\n".join(lines)


def reasoning_mode_prompt(mode: ReasoningMode) -> str:
    """Return a prompt injection string for the given reasoning mode.

    Convenience wrapper around get_reasoning_policy + reasoning_policy_prompt.
    """
    policy = get_reasoning_policy(mode)
    return reasoning_policy_prompt(policy)
