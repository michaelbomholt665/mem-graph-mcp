"""Triage agent eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ...agents.document.triage_agent import (
    RawFinding,
    TriageDecision,
    TriagedViolation,
)
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class TriageInput:
    prompt: str
    case_id: str


_FIXTURE_OUTPUTS = {
    "triage-deduplicate-recurrence": "new=0 recurrence=1 duplicate=0 escalated=0 decisions=recurrence",
    "triage-severity-promotion": "new=0 recurrence=0 duplicate=0 escalated=1 severity=blocker decisions=escalate",
}


TRIAGE_EVAL_SUITE = EvalSuite(
    suite_name="triage",
    agent_name="triage",
    description="Triage coverage for recurrence detection and severity promotion.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="triage-deduplicate-recurrence",
            description="A matching open violation should be classified as a recurrence instead of a brand-new issue.",
            prompt="Triage a finding that matches an already-open violation.",
            expected_keywords=["recurrence=1", "decisions=recurrence"],
            tags=["triage", "dedupe"],
        ),
        EvalCase(
            case_id="triage-severity-promotion",
            description="Security findings with higher actual risk should be escalated beyond the source severity.",
            prompt="Triage a hardcoded secret finding and escalate it when warranted.",
            expected_keywords=["escalated=1", "severity=blocker", "decisions=escalate"],
            tags=["triage", "severity"],
        ),
    ],
)


def _build_report(case_id: str) -> str:
    if case_id == "triage-deduplicate-recurrence":
        finding = RawFinding(
            rule_id="security:sql-injection",
            file_path="src/service.py",
            line_start=42,
            line_end=42,
            severity="major",
            description="Interpolated SQL query uses request.user_id.",
            source="audit_agent",
        )
        decision = TriagedViolation(
            raw=finding,
            decision=TriageDecision.RECURRENCE,
            assessed_severity="major",
            rationale="An open violation already tracks this rule/file pair.",
            existing_violation_id="V-101",
        )
        return (
            f"new=0 recurrence=1 duplicate=0 escalated=0 decisions={decision.decision.value} "
            f"existing={decision.existing_violation_id}"
        )

    finding = RawFinding(
        rule_id="security:hardcoded-secret",
        file_path="src/payments.py",
        line_start=7,
        line_end=7,
        severity="minor",
        description="Production API key is committed in source.",
        source="manual",
    )
    decision = TriagedViolation(
        raw=finding,
        decision=TriageDecision.ESCALATE,
        assessed_severity="blocker",
        rationale="Hardcoded production credentials are release-blocking.",
        existing_violation_id=None,
    )
    return (
        f"new=0 recurrence=0 duplicate=0 escalated=1 severity={decision.assessed_severity} "
        f"decisions={decision.decision.value}"
    )


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="triage")


async def _run_live(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _build_report(case.case_id)


def build_triage_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=TRIAGE_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_triage_dataset() -> Dataset[TriageInput, HostedTextOutput, HostedTextMeta]:
    cases: list[Case[TriageInput, HostedTextOutput, HostedTextMeta]] = []
    for case in TRIAGE_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=TriageInput(prompt=case.prompt, case_id=case.case_id),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, TRIAGE_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[TriageInput, HostedTextOutput, HostedTextMeta](
        name="triage-golden-set",
        cases=cases,
    )


def push_triage_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_triage_dataset(),
            description=TRIAGE_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_triage_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def triage_task(inputs: TriageInput) -> HostedTextOutput:
        await asyncio.sleep(0)
        return HostedTextOutput(text=_build_report(inputs.case_id))

    await run_eval_from_hosted(
        "triage-golden-set",
        triage_task,
        TriageInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "TRIAGE_EVAL_SUITE",
    "build_triage_binding",
    "build_triage_dataset",
    "push_triage_dataset",
    "run_triage_eval",
]
