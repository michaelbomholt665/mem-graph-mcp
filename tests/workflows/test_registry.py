"""Tests for the workflow registry."""

from __future__ import annotations

import pytest

from mem_graph.resources.workflows.models import ProfileSize, ReasoningMode
from mem_graph.resources.workflows.registry import (
    all_workflows,
    get_workflow,
    register_workflow,
    workflow_registry,
)
from mem_graph.resources.workflows.models import WorkflowResource


# ---------------------------------------------------------------------------
# Built-in workflows
# ---------------------------------------------------------------------------


def test_registry_has_autopilot_workflow() -> None:
    wf = get_workflow("autopilot_graph")
    assert wf is not None
    assert wf.key == "autopilot_graph"


def test_registry_has_managed_workflow() -> None:
    wf = get_workflow("managed_workflow_graph")
    assert wf is not None
    assert wf.key == "managed_workflow_graph"


def test_registry_has_package_audit() -> None:
    wf = get_workflow("package_audit")
    assert wf is not None
    assert wf.key == "package_audit"


# ---------------------------------------------------------------------------
# Group A workflows
# ---------------------------------------------------------------------------

_GROUP_A_KEYS = [
    "feature_implementation",
    "refactor",
    "research",
    "security_hardening",
    "performance_profiling",
    "adr_authoring",
    "feature_design",
    "schema_design",
    "api_contract_design",
    "design_docs",
    "runbook_authoring",
    "disaster_recovery",
    "command_design",
    "error_logging_design",
    "dependency_audit",
    "ci_setup",
    "docs_generation",
    "changelog_authoring",
    "onboarding_docs",
    "release_preparation",
    "deployment_validation",
    "utility_extraction",
    "implementation_planning",
    "project_scaffold",
]


@pytest.mark.parametrize("key", _GROUP_A_KEYS)
def test_group_a_workflow_registered(key: str) -> None:
    """Every Group A workflow must be retrievable by key."""
    wf = get_workflow(key)
    assert wf is not None, f"Workflow '{key}' not found in registry."
    assert wf.key == key


def test_group_a_count_is_24() -> None:
    """Exactly 24 Group A workflows are registered."""
    reg = workflow_registry()
    group_a_found = [k for k in _GROUP_A_KEYS if k in reg]
    assert len(group_a_found) == 24


def test_all_workflows_returns_list() -> None:
    wfs = all_workflows()
    assert isinstance(wfs, list)
    assert len(wfs) >= 27  # 3 built-ins + 24 Group A


def test_workflow_registry_returns_dict() -> None:
    reg = workflow_registry()
    assert isinstance(reg, dict)
    assert "autopilot_graph" in reg


# ---------------------------------------------------------------------------
# Workflow metadata
# ---------------------------------------------------------------------------


def test_all_workflows_have_display_name() -> None:
    for wf in all_workflows():
        assert wf.display_name, f"Workflow '{wf.key}' missing display_name."


def test_all_workflows_have_description() -> None:
    for wf in all_workflows():
        assert wf.description, f"Workflow '{wf.key}' missing description."


def test_all_workflows_have_valid_profile_size() -> None:
    valid_sizes = set(ProfileSize)
    for wf in all_workflows():
        assert wf.profile in valid_sizes, (
            f"Workflow '{wf.key}' has invalid profile: {wf.profile!r}."
        )


def test_all_workflows_have_valid_reasoning_mode() -> None:
    valid_modes = set(ReasoningMode)
    for wf in all_workflows():
        assert wf.reasoning_mode in valid_modes, (
            f"Workflow '{wf.key}' has invalid reasoning_mode: {wf.reasoning_mode!r}."
        )


def test_all_workflows_have_task_types() -> None:
    for wf in all_workflows():
        assert wf.task_types, f"Workflow '{wf.key}' has no task_types."


def test_all_workflows_have_stages() -> None:
    for wf in all_workflows():
        assert wf.stages, f"Workflow '{wf.key}' has no stages."


# ---------------------------------------------------------------------------
# Runtime registration
# ---------------------------------------------------------------------------


def test_register_workflow_adds_to_registry() -> None:
    new_wf = WorkflowResource(
        key="test_workflow_registry",
        display_name="Test Workflow",
        description="A test workflow for registry tests.",
        profile=ProfileSize.SMALL,
        task_types=["test_task"],
        stages=[],
    )
    register_workflow(new_wf)
    assert get_workflow("test_workflow_registry") is new_wf
