from __future__ import annotations

import pytest

from mem_graph.evals.suites.skill_evals import (
    GO_QUALITY_SKILL_EVAL_SUITE,
    PYTHON_QUALITY_SKILL_EVAL_SUITE,
    SECURITY_SKILL_EVAL_SUITE,
    TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE,
    build_go_quality_skill_binding,
    build_python_quality_skill_binding,
    build_security_skill_binding,
    build_typescript_quality_skill_binding,
)


@pytest.mark.asyncio
@pytest.mark.evals
async def test_python_skill_fixture_binding_returns_expected_outputs() -> None:
    binding = build_python_quality_skill_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is PYTHON_QUALITY_SKILL_EVAL_SUITE
    assert outputs == {
        "skill-python-bare-except": "skill=python_quality detected=python:bare-except rule_count=2",
        "skill-python-clean": "skill=python_quality detected=none rule_count=2",
    }


@pytest.mark.asyncio
@pytest.mark.evals
async def test_security_skill_fixture_binding_returns_expected_outputs() -> None:
    binding = build_security_skill_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is SECURITY_SKILL_EVAL_SUITE
    assert outputs == {
        "skill-security-hardcoded-secret": "skill=security detected=security:hardcoded-secret rule_count=3",
        "skill-security-clean": "skill=security detected=none rule_count=3",
    }


@pytest.mark.asyncio
@pytest.mark.evals
async def test_go_skill_fixture_binding_returns_expected_outputs() -> None:
    binding = build_go_quality_skill_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is GO_QUALITY_SKILL_EVAL_SUITE
    assert outputs == {
        "skill-go-ignored-error": "skill=go_quality detected=go:ignored-error rule_count=4",
        "skill-go-clean": "skill=go_quality detected=none rule_count=4",
    }


@pytest.mark.asyncio
@pytest.mark.evals
async def test_typescript_skill_fixture_binding_returns_expected_outputs() -> None:
    binding = build_typescript_quality_skill_binding("fixture")
    outputs = {case.case_id: await binding.runner(case) for case in binding.suite.cases}

    assert binding.suite is TYPESCRIPT_QUALITY_SKILL_EVAL_SUITE
    assert outputs == {
        "skill-ts-any": "skill=typescript_quality detected=typescript:any rule_count=0",
        "skill-ts-clean": "skill=typescript_quality detected=none rule_count=0",
    }
