"""Fixture-backed eval suite for the audit agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

from ..agents.audit.audit_agent import AuditDependencies, audit_agent
from ..models.audit import AuditReport
from ..models.evals import EvalCase, EvalMode, EvalSuite, ScorerName, SuiteBinding
from .fixtures import load_code_fixtures
from .scorers import HostedTextScorer


@dataclass
class AuditInput:
    prompt: str
    file_content: str
    file_path: str
    language: str = "python"


@dataclass
class AuditOutput:
    text: str


@dataclass
class AuditMeta:
    case_id: str
    description: str
    scorer: ScorerName
    expected_keywords: list[str]
    expected_pattern: str | None
    tags: list[str]
    rule_focus: str
    source: str = "synthetic"

_CODE_FIXTURES = load_code_fixtures()

_FIXTURE_OUTPUTS = {
    "audit-bare-except": (
        "Detected a bare except clause that hides database errors and should be replaced "
        "with explicit exception handling."
    ),
    "audit-hardcoded-secret": (
        "Found a hardcoded secret in source code. The API key should be moved to secure configuration."
    ),
    "audit-clean-function": "No issues found in the clean addition helper.",
}


AUDIT_EVAL_SUITE = EvalSuite(
    suite_name="audit",
    agent_name="audit",
    description="Audit agent baseline suite covering error handling, secret detection, and clean-code sanity.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=3,
    cases=[
        EvalCase(
            case_id="audit-bare-except",
            description="The audit agent should flag broad exception swallowing.",
            prompt="Audit the pre-loaded Python fixture for unsafe exception handling and return an AuditReport.",
            expected_keywords=["bare except", "exception", "error"],
            tags=["critical", "safety"],
            metadata={
                "fixture_key": "AUDIT_BARE_EXCEPT",
                "file_path": "fixtures/audit_bare_except.py",
            },
        ),
        EvalCase(
            case_id="audit-hardcoded-secret",
            description="The audit agent should catch hardcoded credentials.",
            prompt="Audit the pre-loaded Python fixture for secrets and return an AuditReport.",
            expected_keywords=["hardcoded", "secret", "api key"],
            tags=["security"],
            metadata={
                "fixture_key": "AUDIT_HARDCODED_SECRET",
                "file_path": "fixtures/audit_secret.py",
            },
        ),
        EvalCase(
            case_id="audit-clean-function",
            description="The audit agent should avoid inventing issues in clean code.",
            prompt="Audit the pre-loaded Python fixture and confirm whether it is clean. Return an AuditReport.",
            expected_output="no issues found in the clean addition helper",
            scorer="semantic",
            tags=["sanity"],
            metadata={
                "fixture_key": "AUDIT_CLEAN_FUNCTION",
                "file_path": "fixtures/clean_add.py",
            },
        ),
    ],
)


def _render_audit_report(report: AuditReport) -> str:
    findings = [
        f"{finding.rule_id}: {finding.description}"
        for finding in report.all_findings
    ]
    findings_block = "\n".join(findings) if findings else "no issues found"
    return f"{report.summary}\n{findings_block}".strip()


def _fixture_context(file_path: str, code: str) -> str:
    return f"## File: {file_path}\n```python\n{code}\n```"


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _FIXTURE_OUTPUTS[case.case_id]


async def _run_live(case: EvalCase) -> str:
    fixture_key = case.metadata["fixture_key"]
    file_path = case.metadata.get("file_path", "fixtures/eval_fixture.py")
    deps = AuditDependencies(
        package_path="eval-fixture",
        file_extension=".py",
        extra_file_context=_fixture_context(file_path, _CODE_FIXTURES[fixture_key]),
    )
    result = await audit_agent.run(case.prompt, deps=deps)
    return _render_audit_report(result.output)


def build_audit_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=AUDIT_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_audit_dataset() -> Dataset[AuditInput, AuditOutput, AuditMeta]:
    cases: list[Case[AuditInput, AuditOutput, AuditMeta]] = []
    for case in AUDIT_EVAL_SUITE.cases:
        fixture_key = case.metadata["fixture_key"]
        scorer = case.scorer or AUDIT_EVAL_SUITE.default_scorer
        cases.append(
            Case(
                name=case.case_id,
                inputs=AuditInput(
                    prompt=case.prompt,
                    file_content=_CODE_FIXTURES[fixture_key],
                    file_path=case.metadata.get("file_path", "fixtures/eval_fixture.py"),
                ),
                expected_output=AuditOutput(
                    text=case.expected_output or " ".join(case.expected_keywords)
                ),
                metadata=AuditMeta(
                    case_id=case.case_id,
                    description=case.description,
                    scorer=scorer,
                    expected_keywords=list(case.expected_keywords),
                    expected_pattern=case.expected_pattern,
                    tags=list(case.tags),
                    rule_focus="security" if "security" in case.tags else "bugs",
                ),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[AuditInput, AuditOutput, AuditMeta](
        name="audit-golden-set",
        cases=cases,
    )


def push_audit_dataset() -> dict[str, object]:
    from .logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_audit_dataset(),
            description=AUDIT_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_audit_eval() -> None:
    """Fetch the hosted audit dataset and evaluate it against the live agent."""
    from .evaluator import run_eval_from_hosted

    async def audit_task(inputs: AuditInput) -> AuditOutput:
        deps = AuditDependencies(
            package_path="eval-fixture",
            file_extension=".py",
            extra_file_context=_fixture_context(inputs.file_path, inputs.file_content),
        )
        result = await audit_agent.run(inputs.prompt, deps=deps)
        return AuditOutput(text=_render_audit_report(result.output))

    await run_eval_from_hosted(
        "audit-golden-set",
        audit_task,
        AuditInput,
        AuditOutput,
        AuditMeta,
    )
