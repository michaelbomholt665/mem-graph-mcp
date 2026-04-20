from __future__ import annotations

import pytest

from mem_graph.evals.suites.workflow_autopilot_evals import (
    WORKFLOW_AUTOPILOT_EVAL_SUITE,
    build_workflow_autopilot_binding,
)
from mem_graph.evals.suites.workflow_feature_implementation_evals import (
    WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE,
    build_workflow_feature_implementation_binding,
)
from mem_graph.evals.suites.workflow_package_audit_evals import (
    WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE,
    build_workflow_package_audit_binding,
)


@pytest.mark.asyncio
@pytest.mark.evals
async def test_workflow_autopilot_fixture_binding_returns_expected_outputs() -> None:
    binding = build_workflow_autopilot_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is WORKFLOW_AUTOPILOT_EVAL_SUITE
    assert set(outputs) == {
        "workflow-autopilot-clean-pass",
        "workflow-autopilot-guard-rejects",
    }
    assert "success=True" in outputs["workflow-autopilot-clean-pass"]
    assert "retry_count=1" in outputs["workflow-autopilot-guard-rejects"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_workflow_package_audit_fixture_binding_returns_expected_outputs() -> (
    None
):
    binding = build_workflow_package_audit_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE
    assert set(outputs) == {
        "workflow-package-audit-counts",
        "workflow-package-audit-dedupes-critical",
    }
    assert "files=7" in outputs["workflow-package-audit-counts"]
    assert "critical=1" in outputs["workflow-package-audit-dedupes-critical"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_workflow_feature_implementation_fixture_binding_returns_expected_outputs() -> (
    None
):
    binding = build_workflow_feature_implementation_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE
    assert set(outputs) == {
        "workflow-feature-stage-order",
        "workflow-feature-scope-boundary",
    }
    assert "implementation" in outputs["workflow-feature-stage-order"]
    assert "target_files=2" in outputs["workflow-feature-scope-boundary"]
