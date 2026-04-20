"""Tests for the workflow selector."""

from __future__ import annotations

import pytest

from mem_graph.resources.workflows.models import ProfileSize, ReasoningMode
from mem_graph.resources.workflows.selector import (
    WorkflowSelection,
    select_all,
    select_profile,
    select_reasoning_policy,
    select_workflow,
)


# ---------------------------------------------------------------------------
# select_workflow
# ---------------------------------------------------------------------------


def test_select_workflow_returns_workflow_by_task_type() -> None:
    wf = select_workflow("package_audit")
    assert wf.key == "package_audit"


def test_select_workflow_preferred_key_wins() -> None:
    wf = select_workflow("remediation", preferred_key="autopilot_graph")
    assert wf.key == "autopilot_graph"


def test_select_workflow_falls_back_to_managed() -> None:
    wf = select_workflow("unknown_task_xyz_123")
    assert wf.key == "managed_workflow_graph"


def test_select_workflow_group_a_task_type() -> None:
    wf = select_workflow("feature_implementation")
    assert wf.key == "feature_implementation"


def test_select_workflow_research_task_type() -> None:
    wf = select_workflow("research")
    assert wf.key == "research"


# ---------------------------------------------------------------------------
# select_profile
# ---------------------------------------------------------------------------


def test_select_profile_size_override_wins() -> None:
    profile = select_profile("remediation", size_override=ProfileSize.SMALL)
    assert profile.size == ProfileSize.SMALL


def test_select_profile_large_file_count_upgrades_to_large() -> None:
    profile = select_profile("bug_fix", file_count=25)
    assert profile.size == ProfileSize.LARGE


def test_select_profile_medium_file_count_upgrades_small_to_medium() -> None:
    profile = select_profile("bug_fix", file_count=6)
    assert profile.size == ProfileSize.MEDIUM


def test_select_profile_high_risk_upgrades_small_to_medium() -> None:
    profile = select_profile("bug_fix", file_count=0, risk_level="high")
    assert profile.size == ProfileSize.MEDIUM


def test_select_profile_default_for_package_audit() -> None:
    profile = select_profile("package_audit")
    assert profile.size == ProfileSize.LARGE


# ---------------------------------------------------------------------------
# select_reasoning_policy
# ---------------------------------------------------------------------------


def test_select_reasoning_policy_default_is_react() -> None:
    policy = select_reasoning_policy()
    assert policy.mode == ReasoningMode.REACT_CHALLENGE


def test_select_reasoning_policy_tot_when_both_flags() -> None:
    policy = select_reasoning_policy(high_ambiguity=True, tot_allowed=True)
    assert policy.mode == ReasoningMode.BOUNDED_TOT


def test_select_reasoning_policy_react_when_only_ambiguity() -> None:
    policy = select_reasoning_policy(high_ambiguity=True, tot_allowed=False)
    assert policy.mode == ReasoningMode.REACT_CHALLENGE


# ---------------------------------------------------------------------------
# select_all
# ---------------------------------------------------------------------------


def test_select_all_returns_workflow_selection() -> None:
    sel = select_all("package_audit")
    assert isinstance(sel, WorkflowSelection)


def test_select_all_workflow_matches_task_type() -> None:
    sel = select_all("feature_implementation")
    assert sel.workflow.key == "feature_implementation"


def test_select_all_profile_adjusted_for_file_count() -> None:
    sel = select_all("bug_fix", file_count=30)
    assert sel.effective_size == ProfileSize.LARGE


def test_select_all_rationale_populated() -> None:
    sel = select_all("research", file_count=5)
    assert sel.rationale


def test_select_all_overridden_flag_when_preferred_key() -> None:
    sel = select_all("research", preferred_key="autopilot_graph")
    assert sel.overridden is True


def test_select_all_not_overridden_by_default() -> None:
    sel = select_all("research")
    assert sel.overridden is False


def test_select_all_sandbox_policy_set() -> None:
    sel = select_all("package_audit")
    assert sel.sandbox_policy is not None


@pytest.mark.parametrize(
    "task_type,expected_key",
    [
        ("remediation", "autopilot_graph"),
        ("package_audit", "package_audit"),
        ("research", "research"),
        ("feature_implementation", "feature_implementation"),
        ("security_hardening", "security_hardening"),
        ("dependency_audit", "dependency_audit"),
        ("implementation_planning", "implementation_planning"),
    ],
)
def test_select_all_task_type_routes_to_workflow(
    task_type: str, expected_key: str
) -> None:
    sel = select_all(task_type)
    assert sel.workflow.key == expected_key
