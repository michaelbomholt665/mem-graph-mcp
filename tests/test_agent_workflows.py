"""Tests for Task 026: Resource-Driven Agent Workflows and Profiled Orchestration."""

from __future__ import annotations

import pytest

################
#   RESOURCE MODELS
################


def test_workflow_resource_is_valid_pydantic():
    from mem_graph.resources.workflows.models import (
        ProfileSize,
        ReasoningMode,
        WorkflowResource,
    )

    wf = WorkflowResource(
        key="test_wf",
        display_name="Test Workflow",
        description="A test workflow.",
        profile=ProfileSize.SMALL,
        task_types=["bug_fix"],
        reasoning_mode=ReasoningMode.REACT_CHALLENGE,
        risk_level="low",
    )
    assert wf.key == "test_wf"
    assert wf.profile == ProfileSize.SMALL
    assert wf.reasoning_mode == ReasoningMode.REACT_CHALLENGE
    assert wf.risk_level == "low"


def test_workflow_stage_definition_depends_on():
    from mem_graph.resources.workflows.models import WorkflowStageDefinition

    stage = WorkflowStageDefinition(
        name="validate",
        description="Run validation.",
        depends_on=["implement"],
        artifacts=["validation_output"],
    )
    assert "implement" in stage.depends_on
    assert "validation_output" in stage.artifacts


################
#   PROFILES
################


def test_profiles_are_three_distinct_sizes():
    from mem_graph.resources.workflows.profiles import PROFILE_MAP, ProfileSize

    assert set(PROFILE_MAP.keys()) == {
        ProfileSize.SMALL,
        ProfileSize.MEDIUM,
        ProfileSize.LARGE,
    }


def test_small_profile_has_minimal_constraints():
    from mem_graph.resources.workflows.profiles import SMALL_PROFILE

    assert SMALL_PROFILE.max_stages <= 3
    assert SMALL_PROFILE.fan_out_limit == 1
    assert SMALL_PROFILE.retry_cycles == 0


def test_medium_profile_allows_limited_fan_out():
    from mem_graph.resources.workflows.profiles import MEDIUM_PROFILE

    assert 1 < MEDIUM_PROFILE.fan_out_limit <= 4
    assert MEDIUM_PROFILE.retry_cycles >= 1


def test_large_profile_has_checkpoints_and_high_fan_out():
    from mem_graph.resources.workflows.profiles import LARGE_PROFILE

    assert LARGE_PROFILE.fan_out_limit >= 4
    assert LARGE_PROFILE.retry_cycles >= 2
    assert LARGE_PROFILE.checkpoint_frequency > 0


def test_get_profile_returns_correct_instance():
    from mem_graph.resources.workflows.profiles import (
        LARGE_PROFILE,
        ProfileSize,
        get_profile,
    )

    result = get_profile(ProfileSize.LARGE)
    assert result is LARGE_PROFILE


################
#   REASONING POLICIES
################


def test_react_challenge_policy_has_required_steps():
    from mem_graph.resources.workflows.reasoning import (
        REACT_CHALLENGE_POLICY,
        ReasoningMode,
    )

    assert REACT_CHALLENGE_POLICY.mode == ReasoningMode.REACT_CHALLENGE
    assert len(REACT_CHALLENGE_POLICY.required_steps) == 4
    step_names = [s.split(":")[0] for s in REACT_CHALLENGE_POLICY.required_steps]
    assert step_names == ["observe", "draft", "challenge", "decide"]


def test_bounded_tot_has_width_depth_and_pruning():
    from mem_graph.resources.workflows.reasoning import BOUNDED_TOT_POLICY

    assert BOUNDED_TOT_POLICY.tree_width >= 2
    assert BOUNDED_TOT_POLICY.tree_depth >= 1
    assert len(BOUNDED_TOT_POLICY.pruning_criteria) >= 2
    assert BOUNDED_TOT_POLICY.budget_cap > 0


def test_react_challenge_prompt_contains_all_steps():
    from mem_graph.resources.workflows.reasoning import (
        REACT_CHALLENGE_POLICY,
        reasoning_policy_prompt,
    )

    prompt = reasoning_policy_prompt(REACT_CHALLENGE_POLICY)
    assert "observe" in prompt
    assert "draft" in prompt
    assert "challenge" in prompt
    assert "decide" in prompt
    assert "deterministic gate" in prompt


def test_tot_prompt_contains_constraints():
    from mem_graph.resources.workflows.reasoning import (
        BOUNDED_TOT_POLICY,
        reasoning_policy_prompt,
    )

    prompt = reasoning_policy_prompt(BOUNDED_TOT_POLICY)
    assert "Width" in prompt
    assert "Depth" in prompt
    assert "Pruning" in prompt


################
#   TASK TYPES
################


def test_task_type_profile_map_covers_all_categories():
    from mem_graph.resources.workflows.task_types import (
        TASK_TYPE_CATEGORIES,
        TASK_TYPE_PROFILE_MAP,
    )

    all_types = [t for types in TASK_TYPE_CATEGORIES.values() for t in types]
    for task_type in all_types:
        assert task_type in TASK_TYPE_PROFILE_MAP, f"Missing: {task_type}"


def test_profile_for_task_type_fallback():
    from mem_graph.resources.workflows.task_types import (
        ProfileSize,
        profile_for_task_type,
    )

    assert profile_for_task_type("unknown_task_xyz") == ProfileSize.MEDIUM


def test_task_type_categories_returns_dict():
    from mem_graph.resources.workflows.task_types import all_task_type_categories

    cats = all_task_type_categories()
    assert "small" in cats
    assert "medium" in cats
    assert "large" in cats


################
#   REGISTRY
################


def test_workflow_registry_has_three_builtin_workflows():
    from mem_graph.resources.workflows.registry import all_workflows

    workflows = all_workflows()
    assert len(workflows) == 3


def test_workflow_registry_contains_expected_keys():
    from mem_graph.resources.workflows.registry import workflow_registry

    reg = workflow_registry()
    assert "autopilot_graph" in reg
    assert "managed_workflow_graph" in reg
    assert "package_audit" in reg


def test_get_workflow_returns_none_for_unknown_key():
    from mem_graph.resources.workflows.registry import get_workflow

    assert get_workflow("does_not_exist") is None


def test_register_workflow_adds_to_registry():
    from mem_graph.resources.workflows.models import ProfileSize, WorkflowResource
    from mem_graph.resources.workflows.registry import (
        get_workflow,
        register_workflow,
        workflow_registry,
    )

    wf = WorkflowResource(
        key="test_registration",
        display_name="Test",
        description="Temp.",
        profile=ProfileSize.SMALL,
    )
    register_workflow(wf)
    assert get_workflow("test_registration") is wf
    assert "test_registration" in workflow_registry()
    # cleanup
    from mem_graph.resources.workflows import registry as _reg

    _reg._WORKFLOW_REGISTRY.pop("test_registration", None)


################
#   SELECTOR
################


def test_select_workflow_by_task_type():
    from mem_graph.resources.workflows.selector import select_workflow

    wf = select_workflow("remediation")
    assert wf.key == "autopilot_graph"


def test_select_workflow_prefers_explicit_key():
    from mem_graph.resources.workflows.selector import select_workflow

    wf = select_workflow("bug_fix", preferred_key="managed_workflow_graph")
    assert wf.key == "managed_workflow_graph"


def test_select_workflow_falls_back_for_unknown_type():
    from mem_graph.resources.workflows.selector import select_workflow

    wf = select_workflow("totally_unknown_type_xyz")
    assert wf is not None


def test_select_profile_upgrades_small_to_medium_for_many_files():
    from mem_graph.resources.workflows.models import ProfileSize
    from mem_graph.resources.workflows.selector import select_profile

    profile = select_profile("bug_fix", file_count=10)
    assert profile.size == ProfileSize.MEDIUM


def test_select_profile_upgrades_to_large_for_20_plus_files():
    from mem_graph.resources.workflows.models import ProfileSize
    from mem_graph.resources.workflows.selector import select_profile

    profile = select_profile("bug_fix", file_count=25)
    assert profile.size == ProfileSize.LARGE


def test_select_profile_respects_size_override():
    from mem_graph.resources.workflows.models import ProfileSize
    from mem_graph.resources.workflows.selector import select_profile

    profile = select_profile(
        "remediation", file_count=1, size_override=ProfileSize.SMALL
    )
    assert profile.size == ProfileSize.SMALL


def test_select_reasoning_policy_defaults_to_react():
    from mem_graph.resources.workflows.models import ReasoningMode
    from mem_graph.resources.workflows.selector import select_reasoning_policy

    policy = select_reasoning_policy()
    assert policy.mode == ReasoningMode.REACT_CHALLENGE


def test_select_reasoning_policy_tot_requires_both_flags():
    from mem_graph.resources.workflows.models import ReasoningMode
    from mem_graph.resources.workflows.selector import select_reasoning_policy

    # Only high_ambiguity → still REACT
    p1 = select_reasoning_policy(high_ambiguity=True, tot_allowed=False)
    assert p1.mode == ReasoningMode.REACT_CHALLENGE

    # Both flags → ToT
    p2 = select_reasoning_policy(high_ambiguity=True, tot_allowed=True)
    assert p2.mode == ReasoningMode.BOUNDED_TOT


def test_select_all_returns_complete_selection():
    from mem_graph.resources.workflows.selector import select_all

    sel = select_all("bug_fix", file_count=3)
    assert sel.workflow is not None
    assert sel.profile is not None
    assert sel.reasoning_policy is not None
    assert sel.sandbox_policy is not None
    assert sel.rationale != ""
    assert sel.overridden is False


def test_profile_sandbox_policy_defaults_propagate():
    from mem_graph.resources.workflows.profiles import MEDIUM_PROFILE
    from mem_graph.resources.workflows.selector import select_all

    sel = select_all("remediation", file_count=6)

    assert MEDIUM_PROFILE.sandbox_policy.enabled is True
    assert sel.sandbox_policy.enabled is True
    assert sel.sandbox_policy.network == "none"


def test_select_all_marks_override_when_key_given():
    from mem_graph.resources.workflows.selector import select_all

    sel = select_all("bug_fix", preferred_key="autopilot_graph")
    assert sel.overridden is True
    assert sel.workflow.key == "autopilot_graph"


################
#   VISUALIZATION
################


def test_all_workflow_metadata_matches_registry_count():
    from mem_graph.resources.workflows.registry import all_workflows
    from mem_graph.resources.workflows.visualization import all_workflow_metadata

    meta = all_workflow_metadata()
    assert len(meta) == len(all_workflows())


def test_workflow_metadata_has_required_fields():
    from mem_graph.resources.workflows.visualization import all_workflow_metadata

    for item in all_workflow_metadata():
        assert "key" in item
        assert "display_name" in item
        assert "mermaid" in item
        assert "nodes" in item
        assert "edges" in item


def test_mermaid_contains_graph_td():
    from mem_graph.resources.workflows.registry import get_workflow
    from mem_graph.resources.workflows.visualization import workflow_to_mermaid

    wf = get_workflow("autopilot_graph")
    assert wf is not None
    mermaid = workflow_to_mermaid(wf)
    assert mermaid.startswith("graph TD")
    assert "context_gather" in mermaid or "sentry" in mermaid


################
#   DISCOVERY.PY — REGISTRY-DRIVEN
################


def test_workflow_definitions_returns_registry_data():
    from mem_graph.agents.discovery import workflow_definitions

    defs = workflow_definitions()
    keys = {d["key"] for d in defs}
    assert "autopilot_graph" in keys
    assert "managed_workflow_graph" in keys
    assert "package_audit" in keys


def test_workflow_definitions_have_no_static_duplicate_declarations():
    """Ensure discovery.py no longer contains hardcoded _known_workflows()."""
    from mem_graph.agents import discovery

    assert not hasattr(discovery, "_known_workflows"), (
        "discovery.py still has static _known_workflows — should be removed."
    )


################
#   PACKAGE AUDIT RUNTIME
################


def test_chunk_files_produces_correct_sizes():
    from mem_graph.workflows.runtime.package_audit_runtime import _chunk_files

    files = [f"file_{i}.py" for i in range(12)]
    chunks = _chunk_files(files, 5)
    assert len(chunks) == 3
    assert len(chunks[0]) == 5
    assert len(chunks[2]) == 2


def test_deduplicate_findings_removes_identical_keys():
    from mem_graph.workflows.runtime.package_audit_runtime import (
        ChunkFinding,
        _deduplicate_findings,
    )

    findings = [
        ChunkFinding(file_path="a.py", rule="R001", description="Issue"),
        ChunkFinding(file_path="a.py", rule="R001", description="Issue"),
        ChunkFinding(file_path="b.py", rule="R002", description="Other"),
    ]
    deduped = _deduplicate_findings(findings)
    assert len(deduped) == 2


def test_rank_findings_orders_by_severity():
    from mem_graph.workflows.runtime.package_audit_runtime import (
        ChunkFinding,
        _rank_findings,
    )

    findings = [
        ChunkFinding(file_path="a.py", rule="R", severity="low", description="Low"),
        ChunkFinding(
            file_path="b.py", rule="R", severity="critical", description="Crit"
        ),
        ChunkFinding(file_path="c.py", rule="R", severity="high", description="High"),
    ]
    ranked = _rank_findings(findings)
    severities = [f.severity for f in ranked]
    assert severities == ["critical", "high", "low"]


@pytest.mark.asyncio
async def test_run_package_audit_dry_run_produces_report(tmp_path):
    """run_package_audit in dry-run mode produces a valid report structure."""
    from mem_graph.workflows.runtime.package_audit_runtime import (
        PackageAuditDeps,
        run_package_audit,
    )

    # Create a small temp package with some Python files
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    for i in range(6):
        (pkg / f"module_{i}.py").write_text(f"# module {i}\ndef func_{i}(): pass\n")

    deps = PackageAuditDeps(
        package_paths=[str(pkg)],
        chunk_size=4,
        execute_agents=False,
    )
    report = await run_package_audit(deps)

    assert report.total_packages == 1
    assert report.total_files == 6
    assert report.total_chunks == 2  # 6 files / chunk_size 4 → ceil(6/4)=2
    assert "6 file(s)" in report.summary
    assert len(report.critical_findings) == 0  # dry-run → no real agents


@pytest.mark.asyncio
async def test_run_package_audit_skips_missing_path():
    from mem_graph.workflows.runtime.package_audit_runtime import (
        PackageAuditDeps,
        run_package_audit,
    )

    deps = PackageAuditDeps(
        package_paths=["/does/not/exist/at/all"],
        execute_agents=False,
    )
    report = await run_package_audit(deps)
    assert report.total_packages == 0
    assert report.total_files == 0


################
#   ORCHESTRATOR RUNTIME
################


def test_orchestrator_runtime_re_exports_autopilot_graph():
    from mem_graph.workflows.runtime import orchestrator_runtime

    assert hasattr(orchestrator_runtime, "autopilot_graph")
    assert hasattr(orchestrator_runtime, "autopilot_graph_run")
    assert hasattr(orchestrator_runtime, "autopilot_graph_run_with_selection")


def test_managed_workflow_runtime_re_exports():
    from mem_graph.workflows.runtime import managed_workflow_runtime

    assert hasattr(managed_workflow_runtime, "run_managed_workflow")
    assert hasattr(managed_workflow_runtime, "run_managed_workflow_with_selection")
