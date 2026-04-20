"""Codebase orchestrator eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic_ai.usage import RunUsage
from pydantic_evals import Case, Dataset

from ...agents.orchestrator_agent import (
    BatchFileContent,
    OrchestratorDependencies,
    register_subagent,
    run_orchestrator_batches,
)
from ...models.audit import (
    AuditFinding,
    AuditReport,
    AuditStats,
    FileAuditResult,
    FindingCategory,
    Severity,
)
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class OrchestratorInput:
    prompt: str
    case_id: str


_FIXTURE_OUTPUTS = {
    "orchestrator-audit-aggregate": "batches=2 files=3 findings=3 failed_batches=0 partial_failure=False",
    "orchestrator-partial-failure": "batches=2 files=3 findings=1 failed_batches=1 partial_failure=True",
}


ORCHESTRATOR_EVAL_SUITE = EvalSuite(
    suite_name="orchestrator",
    agent_name="orchestrator",
    description="Orchestrator coverage for batched dispatch, aggregation, and partial-failure handling.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="orchestrator-audit-aggregate",
            description="A successful batched audit should merge findings across batches.",
            prompt="Run the audit orchestrator over three files and summarise the aggregate report.",
            expected_keywords=["batches=2", "findings=3", "partial_failure=False"],
            tags=["orchestration", "aggregation"],
        ),
        EvalCase(
            case_id="orchestrator-partial-failure",
            description="A failed batch should be surfaced as a partial failure without losing successful batch output.",
            prompt="Run the audit orchestrator where one batch times out or fails and summarise the aggregate report.",
            expected_keywords=[
                "failed_batches=1",
                "partial_failure=True",
                "findings=1",
            ],
            tags=["orchestration", "failure"],
        ),
    ],
)


def _build_audit_report(
    deps: OrchestratorDependencies,
    files: list[BatchFileContent],
    *,
    findings_per_file: int,
) -> AuditReport:
    file_results: list[FileAuditResult] = []
    all_findings: list[AuditFinding] = []
    for file_index, file in enumerate(files, start=1):
        findings = [
            AuditFinding(
                rule_id="CWE-703",
                category=FindingCategory.SILENT_ERROR,
                severity=Severity.MAJOR,
                file_path=file.path,
                line_start=1,
                line_end=1,
                description=f"Synthetic swallowed-error finding {finding_index} for {file.path}.",
                suggested_fix="Raise a specific exception instead of swallowing the failure.",
                code_snippet=file.content.splitlines()[0] if file.content else "pass",
            )
            for finding_index in range(1, findings_per_file + 1)
        ]
        all_findings.extend(findings)
        file_results.append(FileAuditResult(file_path=file.path, findings=findings))

    stats = AuditStats(
        total_files_analysed=len(files),
        total_files_skipped=0,
        total_findings=len(all_findings),
        by_severity={Severity.MAJOR.value: len(all_findings)},
        by_category={FindingCategory.SILENT_ERROR.value: len(all_findings)},
        blocker_count=0,
        critical_count=0,
    )
    return AuditReport(
        package_path=deps.package_path,
        summary=f"Synthetic audit covered {len(files)} file(s).",
        file_results=file_results,
        stats=stats,
        rules_applied=["CWE-703"],
    )


async def _aggregate_runner(
    deps: OrchestratorDependencies,
    files: list[BatchFileContent],
    job_usage: RunUsage | None = None,
) -> AuditReport:
    await asyncio.sleep(0)
    return _build_audit_report(deps, files, findings_per_file=1)


async def _partial_failure_runner(
    deps: OrchestratorDependencies,
    files: list[BatchFileContent],
    job_usage: RunUsage | None = None,
) -> AuditReport:
    await asyncio.sleep(0)
    if any("module_2" in file.path for file in files):
        raise RuntimeError("synthetic batch failure")
    return _build_audit_report(deps, files, findings_per_file=1)


def _render_orchestrator_report(report) -> str:
    findings = getattr(report.aggregate, "all_findings", [])
    return (
        f"batches={report.total_batches} files={report.total_files} findings={len(findings)} "
        f"failed_batches={report.failed_batches} partial_failure={report.partial_failure}"
    )


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(
        _FIXTURE_OUTPUTS,
        case.case_id,
        suite_name="orchestrator",
    )


async def _run_live(case: EvalCase) -> str:
    runner_name = (
        "eval-orchestrator-partial"
        if case.case_id == "orchestrator-partial-failure"
        else "eval-orchestrator-aggregate"
    )
    register_subagent("eval-orchestrator-aggregate", _aggregate_runner)
    register_subagent("eval-orchestrator-partial", _partial_failure_runner)

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        for index in range(3):
            (root / f"module_{index}.py").write_text(
                f"print({index})\n",
                encoding="utf-8",
            )

        deps = OrchestratorDependencies(
            package_path=str(root),
            project_id="proj-evals",
            subagent_name=runner_name,
            batch_size=2,
            timeout=5.0,
        )
        report = await run_orchestrator_batches(deps)
        return _render_orchestrator_report(report)


def build_orchestrator_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=ORCHESTRATOR_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_orchestrator_dataset() -> Dataset[
    OrchestratorInput,
    HostedTextOutput,
    HostedTextMeta,
]:
    cases: list[Case[OrchestratorInput, HostedTextOutput, HostedTextMeta]] = []
    for case in ORCHESTRATOR_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=OrchestratorInput(prompt=case.prompt, case_id=case.case_id),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, ORCHESTRATOR_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[OrchestratorInput, HostedTextOutput, HostedTextMeta](
        name="orchestrator-golden-set",
        cases=cases,
    )


def push_orchestrator_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_orchestrator_dataset(),
            description=ORCHESTRATOR_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_orchestrator_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def orchestrator_task(inputs: OrchestratorInput) -> HostedTextOutput:
        case = next(
            case
            for case in ORCHESTRATOR_EVAL_SUITE.cases
            if case.case_id == inputs.case_id
        )
        return HostedTextOutput(text=await _run_live(case))

    await run_eval_from_hosted(
        "orchestrator-golden-set",
        orchestrator_task,
        OrchestratorInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "ORCHESTRATOR_EVAL_SUITE",
    "build_orchestrator_binding",
    "build_orchestrator_dataset",
    "push_orchestrator_dataset",
    "run_orchestrator_eval",
]
