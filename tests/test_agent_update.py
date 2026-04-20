#!/usr/bin/env python3
# tests/test_agent_update.py

import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import asyncio

import pytest

from mem_graph.agents.audit.factory import build_audit_agent_bundle
from mem_graph.agents.audit.rules import audit_rules_get
from mem_graph.agents.builder.agent_builder import (
    HelperAgentSpec,
    discover_helper_agent_specs,
    find_helper_agent_spec,
    propose_helper_agent_update,
    update_helper_agent_spec,
    write_helper_agent_spec,
)
from mem_graph.agents.orchestrator_agent import (
    BatchFileContent,
    OrchestratorDependencies,
    register_subagent,
    run_orchestrator_batches,
)
from mem_graph.agents.router_agent import RouterDecision, WorkflowPlan
from mem_graph.agents.workflow_graph import run_managed_workflow
from mem_graph.config import ModelTier
from mem_graph.evals.logfire_client import describe_dataset_capabilities


@pytest.mark.asyncio
async def test_deterministic_orchestrator_batches_and_aggregates(tmp_path):
    src = tmp_path / "pkg"
    src.mkdir()
    for index in range(3):
        (src / f"file_{index}.py").write_text(f"print({index})\n", encoding="utf-8")

    async def fake_runner(
        deps: OrchestratorDependencies,
        files: list[BatchFileContent],
        job_usage: object = None,
    ) -> object:
        await asyncio.sleep(0)
        return {"count": len(files), "project_id": deps.project_id}

    register_subagent("fake", fake_runner)
    deps = OrchestratorDependencies(
        package_path=str(src),
        project_id="proj",
        subagent_name="fake",
        batch_size=2,
    )

    report = await run_orchestrator_batches(deps)

    assert report.total_files == 3
    assert report.total_batches == 2
    assert report.failed_batches == 0
    assert [len(batch.files_processed) for batch in report.batch_results] == [2, 1]
    assert report.summary.startswith("completed: fake processed 3 file(s)")


def test_agent_builder_discovers_specs_and_protects_existing_files(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    report = discover_helper_agent_specs(tmp_path, "project-x")

    assert [spec.helper_type for spec in report.recommended_specs] == [
        "codebase-aware",
        "command-map",
        "memory-bank-builder",
    ]
    spec = report.recommended_specs[0]
    spec_path, tracking_path = write_helper_agent_spec(spec, tmp_path, "project-x")
    assert spec_path.exists()
    assert tracking_path.exists()

    with pytest.raises(FileExistsError):
        write_helper_agent_spec(spec, tmp_path, "project-x")

    found = find_helper_agent_spec(tmp_path, "project-x", "codebase-aware")
    assert found is not None
    assert found.name == spec.name


def test_agent_builder_validates_registry_links_and_updates_version():
    spec = HelperAgentSpec(
        name="demo",
        helper_type="codebase-aware",
        purpose="Understand architecture.",
        persona_key="architect",
        prompt_key="agent_builder_discovery",
        recommended_model="openai:gpt-5.4-mini",
    )

    updated = update_helper_agent_spec(
        spec,
        proposed_changes={"purpose": "Understand architecture and conventions."},
        reason="Tighten purpose from eval feedback.",
    )

    assert updated.version == 2
    assert updated.purpose.endswith("conventions.")
    assert updated.changelog[-1].startswith("v2:")

    with pytest.raises(ValueError):
        HelperAgentSpec(
            name="bad",
            helper_type="codebase-aware",
            purpose="bad",
            persona_key="missing",
            prompt_key="agent_builder_discovery",
            recommended_model="openai:gpt-5.4-mini",
        )


def test_agent_builder_proposes_eval_driven_update(tmp_path):
    report_path = tmp_path / "eval-report.json"
    report_path.write_text(
        """
{
  "mode": "fixture",
  "total_suites": 1,
  "passed_suites": 0,
  "suite_pass_rate": 0.0,
  "total_duration_ms": 1.0,
  "started_at": "2026-04-18T00:00:00Z",
  "completed_at": "2026-04-18T00:00:01Z",
  "suite_results": [
    {
      "suite_name": "map",
      "agent_name": "mapper",
      "case_count": 1,
      "passed_case_count": 0,
      "case_pass_rate": 0.0,
      "run_count": 1,
      "passed": false,
      "total_duration_ms": 1.0,
      "started_at": "2026-04-18T00:00:00Z",
      "completed_at": "2026-04-18T00:00:01Z",
      "case_results": [
        {
          "case_id": "case-1",
          "description": "detect feature",
          "scorer": "keywords",
          "run_count": 1,
          "pass_count": 0,
          "pass_rate": 0.0,
          "average_score": 0.0,
          "average_duration_ms": 1.0,
          "passed": false,
          "runs": [],
          "failure_details": [
            {
              "run_index": 1,
              "reason": "missing keyword",
              "score": 0.0,
              "output_excerpt": "none",
              "error": null
            }
          ]
        }
      ]
    }
  ]
}
""",
        encoding="utf-8",
    )
    spec = HelperAgentSpec(
        name="demo",
        helper_type="codebase-aware",
        purpose="Understand architecture.",
        persona_key="architect",
        prompt_key="agent_builder_discovery",
        recommended_model="openai:gpt-5.4-mini",
        system_prompt="Base prompt.",
    )

    proposal = propose_helper_agent_update(spec, local_eval_report_path=report_path)

    assert proposal.should_update is True
    assert proposal.failure_patterns == ["map/case-1: missing keyword"]
    assert "Eval Failure Patterns" in proposal.recommended_changes["system_prompt"]


def test_audit_rule_sets_and_factory():
    security_rules = audit_rules_get("security")
    bundle = build_audit_agent_bundle(
        package_path="/tmp/project",
        rule_set="security",
        tool_mode="preloaded",
        extra_file_context="### file.py\npass",
    )

    assert [rule.rule_id for rule in bundle.rules] == [
        rule.rule_id for rule in security_rules
    ]
    assert bundle.tool_mode == "preloaded"


def test_router_decision_defaults_to_route_only():
    decision = RouterDecision(
        tier=ModelTier.TURBO,
        file_count=0,
        concurrency=1,
        intent="audit",
        summary="route only",
    )

    assert decision.workflow_mode == "route_only"
    assert decision.workflow_plan is None


@pytest.mark.asyncio
async def test_managed_workflow_runs_all_default_stages():
    plan = WorkflowPlan(
        objective="Implement a small change and sync memory.",
        project_id="proj",
        target_files=["src/example.py"],
        model_overrides={"implementation": "openai:gpt-5.4-xhigh"},
    )

    state = await run_managed_workflow(plan)

    assert [result.stage for result in state.stage_results] == [
        "context_gather",
        "planning",
        "implementation",
        "audit",
        "debug_validation",
        "documentation",
        "context_map_update",
        "memory_bank_sync",
    ]
    assert state.stage_results[2].model == "openai:gpt-5.4-xhigh"
    assert "Workflow completed" in state.final_report


def test_logfire_dataset_capability_detection_is_offline():
    capabilities = describe_dataset_capabilities()

    assert capabilities.can_list_datasets is True
    assert capabilities.can_get_dataset is True
