from __future__ import annotations

import pytest

from mem_graph.evals.suites.chat_evals import CHAT_EVAL_SUITE, build_chat_binding
from mem_graph.evals.suites.orchestrator_evals import (
    ORCHESTRATOR_EVAL_SUITE,
    build_orchestrator_binding,
)
from mem_graph.evals.suites.router_evals import ROUTER_EVAL_SUITE, build_router_binding
from mem_graph.evals.suites.rule_injector_evals import (
    RULE_INJECTOR_EVAL_SUITE,
    build_rule_injector_binding,
)
from mem_graph.evals.suites.sentry_evals import SENTRY_EVAL_SUITE, build_sentry_binding
from mem_graph.evals.suites.triage_evals import TRIAGE_EVAL_SUITE, build_triage_binding


@pytest.mark.asyncio
@pytest.mark.evals
async def test_router_fixture_binding_returns_expected_outputs() -> None:
    binding = build_router_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is ROUTER_EVAL_SUITE
    assert set(outputs) == {
        "router-single-file-fix",
        "router-large-audit",
        "router-workflow-plan",
    }
    assert "tier=micro" in outputs["router-single-file-fix"]
    assert "mode=subagent_workflow" in outputs["router-workflow-plan"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_sentry_fixture_binding_returns_expected_outputs() -> None:
    binding = build_sentry_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is SENTRY_EVAL_SUITE
    assert set(outputs) == {"sentry-pytest-framework", "sentry-scope-focus"}
    assert "framework=pytest" in outputs["sentry-pytest-framework"]
    assert "scope" in outputs["sentry-scope-focus"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_orchestrator_fixture_binding_returns_expected_outputs() -> None:
    binding = build_orchestrator_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is ORCHESTRATOR_EVAL_SUITE
    assert set(outputs) == {
        "orchestrator-audit-aggregate",
        "orchestrator-partial-failure",
    }
    assert "partial_failure=False" in outputs["orchestrator-audit-aggregate"]
    assert "failed_batches=1" in outputs["orchestrator-partial-failure"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_triage_fixture_binding_returns_expected_outputs() -> None:
    binding = build_triage_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is TRIAGE_EVAL_SUITE
    assert set(outputs) == {
        "triage-deduplicate-recurrence",
        "triage-severity-promotion",
    }
    assert "recurrence=1" in outputs["triage-deduplicate-recurrence"]
    assert "severity=blocker" in outputs["triage-severity-promotion"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_chat_fixture_binding_returns_expected_outputs() -> None:
    binding = build_chat_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is CHAT_EVAL_SUITE
    assert set(outputs) == {"chat-grounded-answer", "chat-no-code-changes"}
    assert "sources=M-001,D-001,V-002" in outputs["chat-grounded-answer"]
    assert "no_code_changes=true" in outputs["chat-no-code-changes"]


@pytest.mark.asyncio
@pytest.mark.evals
async def test_rule_injector_fixture_binding_returns_expected_outputs() -> None:
    binding = build_rule_injector_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is RULE_INJECTOR_EVAL_SUITE
    assert set(outputs) == {
        "rule-injector-python-selection",
        "rule-injector-go-exclusion",
    }
    assert "python:bare-except" in outputs["rule-injector-python-selection"]
    assert "excluded=python:bare-except" in outputs["rule-injector-go-exclusion"]
