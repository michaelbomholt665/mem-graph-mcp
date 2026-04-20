"""Tests for reasoning mode policies and prompt injection."""

from __future__ import annotations

import pytest

from mem_graph.resources.workflows.models import ReasoningMode
from mem_graph.resources.workflows.reasoning import (
    BOUNDED_TOT_POLICY,
    COT_POLICY,
    REACT_2_POLICY,
    REACT_CHALLENGE_POLICY,
    REASONING_POLICY_MAP,
    get_reasoning_policy,
    reasoning_mode_prompt,
    reasoning_policy_prompt,
)


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------


def test_react_challenge_mode() -> None:
    assert REACT_CHALLENGE_POLICY.mode == ReasoningMode.REACT_CHALLENGE


def test_react_2_mode() -> None:
    assert REACT_2_POLICY.mode == ReasoningMode.REACT_2


def test_bounded_tot_mode() -> None:
    assert BOUNDED_TOT_POLICY.mode == ReasoningMode.BOUNDED_TOT


def test_cot_mode() -> None:
    assert COT_POLICY.mode == ReasoningMode.COT


def test_all_policies_have_required_steps() -> None:
    for mode, policy in REASONING_POLICY_MAP.items():
        assert policy.required_steps, f"Policy {mode} has no required_steps."


def test_all_policies_have_description() -> None:
    for mode, policy in REASONING_POLICY_MAP.items():
        assert policy.description, f"Policy {mode} has no description."


def test_reasoning_policy_map_covers_all_modes() -> None:
    for mode in ReasoningMode:
        assert mode in REASONING_POLICY_MAP, (
            f"ReasoningMode.{mode.name} not in REASONING_POLICY_MAP."
        )


# ---------------------------------------------------------------------------
# get_reasoning_policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(ReasoningMode))
def test_get_reasoning_policy_returns_policy_for_mode(mode: ReasoningMode) -> None:
    policy = get_reasoning_policy(mode)
    assert policy.mode == mode


# ---------------------------------------------------------------------------
# reasoning_policy_prompt
# ---------------------------------------------------------------------------


def test_react_challenge_prompt_contains_header() -> None:
    text = reasoning_policy_prompt(REACT_CHALLENGE_POLICY)
    assert "## Reasoning Policy: react_challenge" in text


def test_react_2_prompt_contains_steps() -> None:
    text = reasoning_policy_prompt(REACT_2_POLICY)
    assert "plan" in text.lower()
    assert "evaluate" in text.lower()


def test_bounded_tot_prompt_contains_constraints() -> None:
    text = reasoning_policy_prompt(BOUNDED_TOT_POLICY)
    assert "Width" in text
    assert "Depth" in text
    assert "Budget cap" in text
    assert "Pruning Criteria" in text


def test_cot_prompt_contains_chain_constraints() -> None:
    text = reasoning_policy_prompt(COT_POLICY)
    assert "Chain Constraints" in text
    assert "Candidates per step" in text


def test_prompt_ends_with_gate_reminder() -> None:
    for policy in REASONING_POLICY_MAP.values():
        text = reasoning_policy_prompt(policy)
        assert "deterministic gate" in text


# ---------------------------------------------------------------------------
# reasoning_mode_prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(ReasoningMode))
def test_reasoning_mode_prompt_returns_non_empty(mode: ReasoningMode) -> None:
    text = reasoning_mode_prompt(mode)
    assert text


def test_reasoning_mode_prompt_matches_policy_prompt() -> None:
    mode = ReasoningMode.BOUNDED_TOT
    policy = get_reasoning_policy(mode)
    assert reasoning_mode_prompt(mode) == reasoning_policy_prompt(policy)
