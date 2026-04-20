"""Package audit workflow eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic_evals import Case, Dataset

from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ...workflows.runtime.package_audit_runtime import (
    ChunkFinding,
    PackageAuditDeps,
    run_package_audit,
)
from ...workflows.runtime.workflow_sandbox import WorkflowSandboxContext
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class PackageAuditWorkflowInput:
    prompt: str
    case_id: str


_FIXTURE_OUTPUTS = {
    "workflow-package-audit-counts": "packages=1 files=7 chunks=2 critical=0 follow_up=0",
    "workflow-package-audit-dedupes-critical": "packages=1 files=6 chunks=2 critical=1 follow_up=1",
}


WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE = EvalSuite(
    suite_name="workflow_package_audit",
    agent_name="package_audit",
    description="Package audit workflow coverage for file counting, chunking, and deduplicated critical findings.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="workflow-package-audit-counts",
            description="Package audit should report accurate package, file, and chunk counts.",
            prompt="Audit a seven-file package and report counts.",
            expected_keywords=["packages=1", "files=7", "chunks=2"],
            tags=["workflow", "counts"],
        ),
        EvalCase(
            case_id="workflow-package-audit-dedupes-critical",
            description="Duplicate critical findings across chunks should collapse into one follow-up item.",
            prompt="Audit a six-file package with repeated critical findings and report deduped severity buckets.",
            expected_keywords=["critical=1", "follow_up=1"],
            tags=["workflow", "dedupe"],
        ),
    ],
)


def _render_package_audit_report(report) -> str:
    return (
        f"packages={report.total_packages} files={report.total_files} chunks={report.total_chunks} "
        f"critical={len(report.critical_findings)} follow_up={len(report.follow_up_items)}"
    )


async def _run_package_audit_case(case_id: str) -> str:
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir) / "pkg"
        root.mkdir(parents=True, exist_ok=True)
        file_count = 7 if case_id == "workflow-package-audit-counts" else 6
        for index in range(file_count):
            (root / f"module_{index}.py").write_text(
                f"def fn_{index}():\n    return {index}\n",
                encoding="utf-8",
            )

        deps = PackageAuditDeps(
            package_paths=[str(root)],
            chunk_size=5,
            execute_agents=True,
        )

        async def fake_analyze_chunk(
            chunk: list[str],
            file_contents: dict[str, str],
            package: str,
            *,
            execute_agents: bool,
        ) -> list[ChunkFinding]:
            await asyncio.sleep(0)
            del file_contents, package, execute_agents
            if case_id == "workflow-package-audit-counts":
                return []
            return [
                ChunkFinding(
                    file_path="pkg/shared.py",
                    rule="security:hardcoded-secret",
                    severity="critical",
                    description="Duplicated critical secret finding.",
                    line_number=3,
                ),
                ChunkFinding(
                    file_path="pkg/shared.py",
                    rule="security:hardcoded-secret",
                    severity="critical",
                    description="Duplicated critical secret finding.",
                    line_number=3,
                ),
            ]

        async def fake_ensure_workflow_sandbox(
            *args, **kwargs
        ) -> WorkflowSandboxContext:
            del args, kwargs
            await asyncio.sleep(0)
            return WorkflowSandboxContext(
                session_id="sandbox-evals",
                enabled=True,
                status="active",
            )

        async def fake_finalize_workflow_sandbox(
            context: WorkflowSandboxContext,
            *,
            validation_passed: bool,
            manager=None,
        ) -> WorkflowSandboxContext:
            del validation_passed, manager
            await asyncio.sleep(0)
            return context

        async def fake_abort_workflow_sandbox(
            context: WorkflowSandboxContext,
            *,
            manager=None,
        ) -> WorkflowSandboxContext:
            del manager
            await asyncio.sleep(0)
            return context

        with (
            patch(
                "mem_graph.workflows.runtime.package_audit_runtime._analyze_chunk",
                new=fake_analyze_chunk,
            ),
            patch(
                "mem_graph.workflows.runtime.package_audit_runtime.ensure_workflow_sandbox",
                new=fake_ensure_workflow_sandbox,
            ),
            patch(
                "mem_graph.workflows.runtime.package_audit_runtime.finalize_workflow_sandbox",
                new=fake_finalize_workflow_sandbox,
            ),
            patch(
                "mem_graph.workflows.runtime.package_audit_runtime.abort_workflow_sandbox",
                new=fake_abort_workflow_sandbox,
            ),
        ):
            report = await run_package_audit(deps)
        return _render_package_audit_report(report)


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(
        _FIXTURE_OUTPUTS,
        case.case_id,
        suite_name="workflow_package_audit",
    )


async def _run_live(case: EvalCase) -> str:
    return await _run_package_audit_case(case.case_id)


def build_workflow_package_audit_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_workflow_package_audit_dataset() -> Dataset[
    PackageAuditWorkflowInput,
    HostedTextOutput,
    HostedTextMeta,
]:
    cases: list[Case[PackageAuditWorkflowInput, HostedTextOutput, HostedTextMeta]] = []
    for case in WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=PackageAuditWorkflowInput(
                    prompt=case.prompt, case_id=case.case_id
                ),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(
                    case,
                    WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE.default_scorer,
                ),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[PackageAuditWorkflowInput, HostedTextOutput, HostedTextMeta](
        name="workflow-package-audit-golden-set",
        cases=cases,
    )


def push_workflow_package_audit_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_workflow_package_audit_dataset(),
            description=WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_workflow_package_audit_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def workflow_task(
        inputs: PackageAuditWorkflowInput,
    ) -> HostedTextOutput:
        await asyncio.sleep(0)
        return HostedTextOutput(text=await _run_package_audit_case(inputs.case_id))

    await run_eval_from_hosted(
        "workflow-package-audit-golden-set",
        workflow_task,
        PackageAuditWorkflowInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "WORKFLOW_PACKAGE_AUDIT_EVAL_SUITE",
    "build_workflow_package_audit_binding",
    "build_workflow_package_audit_dataset",
    "push_workflow_package_audit_dataset",
    "run_workflow_package_audit_eval",
]
