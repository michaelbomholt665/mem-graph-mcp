"""Sentry agent eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ...agents.validate.sentry_agent import SentryDependencies, sentry_agent
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for, load_code_fixtures
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class SentryInput:
    prompt: str
    language: str
    file_contents: dict[str, str]
    manifest_context: dict[str, str]
    context_violations: list[str]
    context_decisions: list[str]


_CODE_FIXTURES = load_code_fixtures()
_PYTEST_MANIFEST = {
    "pyproject.toml": "[tool.pytest.ini_options]\npythonpath = ['src']\n",
}

_FIXTURE_OUTPUTS = {
    "sentry-pytest-framework": "framework=pytest tests=fixtures/fetch_user.py::test_fetch_user_raises assertion=pytest.raises(RuntimeError)",
    "sentry-scope-focus": "framework=pytest tests=fixtures/fetch_user.py::test_fetch_user_raises rationale=focus on the original bare except failure without widening scope",
}


SENTRY_EVAL_SUITE = EvalSuite(
    suite_name="sentry",
    agent_name="sentry",
    description="Sentry coverage for failing-test proposals, framework detection, and scope discipline.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=2,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="sentry-pytest-framework",
            description="Sentry should infer pytest from project manifests and draft a failing test.",
            prompt="Draft the failing test that proves the fetch_user bug before any fix is written. Return a SentryReport.",
            expected_keywords=["pytest", "test_fetch_user", "raises"],
            tags=["tests", "framework"],
        ),
        EvalCase(
            case_id="sentry-scope-focus",
            description="Sentry should keep the proposal scoped to the original failure instead of redesigning the feature.",
            prompt="Propose the smallest failing test plan for the fetch_user regression and explain the scope guardrails. Return a SentryReport.",
            expected_keywords=["scope", "bare except", "fixtures/fetch_user.py"],
            tags=["tests", "scope"],
        ),
    ],
)


def _base_sentry_input(case: EvalCase) -> SentryInput:
    return SentryInput(
        prompt=case.prompt,
        language="python",
        file_contents={
            "fixtures/fetch_user.py": _CODE_FIXTURES["FIX_BARE_EXCEPT_ORIGINAL"]
        },
        manifest_context=dict(_PYTEST_MANIFEST),
        context_violations=[
            "CWE-703 fixtures/fetch_user.py uses a bare except and swallows database failures."
        ],
        context_decisions=[
            "D-001 Prefer deterministic pytest coverage for regressions."
        ],
    )


def _render_sentry_report(report) -> str:
    tests = [
        f"{test.file_path}::{test.test_name} assertion={test.failing_assertion} rationale={test.rationale}"
        for test in report.test_cases
    ]
    return f"framework={report.framework} tests={' | '.join(tests)} summary={report.summary}"


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="sentry")


async def _run_live(case: EvalCase) -> str:
    payload = _base_sentry_input(case)
    deps = SentryDependencies(
        language=payload.language,
        file_contents=payload.file_contents,
        manifest_context=payload.manifest_context,
        context_violations=payload.context_violations,
        context_decisions=payload.context_decisions,
    )
    result = await sentry_agent.run(case.prompt, deps=deps)
    return _render_sentry_report(result.output)


def build_sentry_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=SENTRY_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_sentry_dataset() -> Dataset[SentryInput, HostedTextOutput, HostedTextMeta]:
    cases: list[Case[SentryInput, HostedTextOutput, HostedTextMeta]] = []
    for case in SENTRY_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=_base_sentry_input(case),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, SENTRY_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[SentryInput, HostedTextOutput, HostedTextMeta](
        name="sentry-golden-set",
        cases=cases,
    )


def push_sentry_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_sentry_dataset(),
            description=SENTRY_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_sentry_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def sentry_task(inputs: SentryInput) -> HostedTextOutput:
        deps = SentryDependencies(
            language=inputs.language,
            file_contents=inputs.file_contents,
            manifest_context=inputs.manifest_context,
            context_violations=inputs.context_violations,
            context_decisions=inputs.context_decisions,
        )
        result = await sentry_agent.run(inputs.prompt, deps=deps)
        return HostedTextOutput(text=_render_sentry_report(result.output))

    await run_eval_from_hosted(
        "sentry-golden-set",
        sentry_task,
        SentryInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "SENTRY_EVAL_SUITE",
    "build_sentry_binding",
    "build_sentry_dataset",
    "push_sentry_dataset",
    "run_sentry_eval",
]
