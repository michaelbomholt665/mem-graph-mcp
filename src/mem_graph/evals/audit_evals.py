"""Fixture-backed eval suite for the audit agent."""

from __future__ import annotations

import asyncio

from ..agents.audit.audit_agent import AuditDependencies, audit_agent
from ..models.audit import AuditReport
from ..models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from .fixtures import load_code_fixtures

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