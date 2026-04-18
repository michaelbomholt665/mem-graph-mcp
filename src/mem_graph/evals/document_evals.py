"""Fixture-backed eval suite for document-oriented agent workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from pydantic_evals import Case, Dataset

from ..agents.document.decision_agent import (
    DecisionDependencies,
    ReviewReport,
    decision_agent,
)
from ..agents.document.task_agent import (
    DecompositionReport,
    TaskDependencies,
    task_agent,
)
from ..models.evals import EvalCase, EvalMode, EvalSuite, ScorerName, SuiteBinding
from .fixtures import format_preloaded_files, load_graph_fixtures
from .scorers import HostedTextScorer


@dataclass
class DocumentInput:
    prompt: str
    workflow: str
    project_id: str
    files: list[dict[str, object]]
    decisions: list[dict[str, object]]


@dataclass
class DocumentOutput:
    text: str


@dataclass
class DocumentMeta:
    case_id: str
    description: str
    scorer: ScorerName
    expected_keywords: list[str]
    expected_pattern: str | None
    tags: list[str]
    source: str = "synthetic"

_GRAPH_FIXTURES = load_graph_fixtures()["document"]

_FIXTURE_OUTPUTS = {
    "document-task-plan": (
        "Planning and green-phase tasks update src/mem_graph/tools/memory/memory.py with "
        "specific acceptance criteria."
    ),
    "document-decision-review": (
        "Decision D-001 is honoured because src/mem_graph/db.py records redacted graph-query metadata."
    ),
}


DOCUMENT_EVAL_SUITE = EvalSuite(
    suite_name="document",
    agent_name="document",
    description="Document agent coverage for task decomposition and decision review.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=3,
    cases=[
        EvalCase(
            case_id="document-task-plan",
            description="The task agent should produce phased work that references the mapped memory file.",
            prompt="Decompose the supplied feature request into implementation tasks and return a DecompositionReport.",
            expected_keywords=[
                "planning",
                "green",
                "src/mem_graph/tools/memory/memory.py",
                "acceptance",
            ],
            metadata={"workflow": "task"},
            tags=["document", "planning"],
        ),
        EvalCase(
            case_id="document-decision-review",
            description="The decision review agent should confirm redacted observability metadata remains honoured.",
            prompt="Review the supplied architectural decision against the pre-loaded files and return a ReviewReport.",
            expected_keywords=[
                "honoured",
                "redacted",
                "src/mem_graph/db.py",
            ],
            metadata={"workflow": "decision"},
            tags=["document", "decisions"],
        ),
    ],
)


def _render_task_report(report: DecompositionReport) -> str:
    task_lines = [
        f"{task.task_id} {task.phase} {task.primary_file or 'no-file'} {task.title}"
        for task in report.tasks
    ]
    criteria = [
        criterion for task in report.tasks for criterion in task.acceptance_criteria
    ]
    parts = [report.summary, *task_lines, *criteria, *report.identified_blockers]
    return "\n".join(part for part in parts if part).strip()


def _render_decision_report(report: ReviewReport) -> str:
    review_lines = [
        f"{review.decision_id} {review.status.value} {' '.join(review.drifted_files)} {review.evidence}"
        for review in report.reviews
    ]
    parts = [report.summary, *review_lines]
    return "\n".join(part for part in parts if part).strip()


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return _FIXTURE_OUTPUTS[case.case_id]


async def _run_live(case: EvalCase) -> str:
    if case.metadata.get("workflow") == "task":
        task_deps = TaskDependencies(
            feature_description=_GRAPH_FIXTURES["feature_description"],
            project_id=load_graph_fixtures()["project_id"],
            codebase_map=list(_GRAPH_FIXTURES["codebase_map"]),
            open_violations=list(_GRAPH_FIXTURES["open_violations"]),
            prior_decisions=list(_GRAPH_FIXTURES["prior_decisions"]),
            skills_content="Prefer redacted observability metadata.",
        )
        task_result = await task_agent.run(case.prompt, deps=task_deps)
        return _render_task_report(task_result.output)

    decision_deps = DecisionDependencies(
        project_id=load_graph_fixtures()["project_id"],
        package_path="eval-fixture",
        decisions=list(_GRAPH_FIXTURES["decisions"]),
        skills_content="Prefer redacted observability metadata.",
        extra_file_context=format_preloaded_files(_GRAPH_FIXTURES["decision_files"]),
    )
    decision_result = await decision_agent.run(case.prompt, deps=decision_deps)
    return _render_decision_report(decision_result.output)


def build_document_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=DOCUMENT_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_document_dataset() -> Dataset[DocumentInput, DocumentOutput, DocumentMeta]:
    fixtures = load_graph_fixtures()
    project_id = fixtures["project_id"]
    cases: list[Case[DocumentInput, DocumentOutput, DocumentMeta]] = []
    for case in DOCUMENT_EVAL_SUITE.cases:
        workflow = case.metadata.get("workflow", "task")
        files = (
            list(_GRAPH_FIXTURES["decision_files"])
            if workflow == "decision"
            else list(_GRAPH_FIXTURES["codebase_map"])
        )
        scorer = case.scorer or DOCUMENT_EVAL_SUITE.default_scorer
        cases.append(
            Case(
                name=case.case_id,
                inputs=DocumentInput(
                    prompt=case.prompt,
                    workflow=workflow,
                    project_id=project_id,
                    files=files,
                    decisions=list(_GRAPH_FIXTURES["decisions"]),
                ),
                expected_output=DocumentOutput(
                    text=case.expected_output or " ".join(case.expected_keywords)
                ),
                metadata=DocumentMeta(
                    case_id=case.case_id,
                    description=case.description,
                    scorer=scorer,
                    expected_keywords=list(case.expected_keywords),
                    expected_pattern=case.expected_pattern,
                    tags=list(case.tags),
                ),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[DocumentInput, DocumentOutput, DocumentMeta](
        name="document-golden-set",
        cases=cases,
    )


def push_document_dataset() -> dict[str, object]:
    from .logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_document_dataset(),
            description=DOCUMENT_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_document_eval() -> None:
    """Fetch the hosted document dataset and evaluate it against live agents."""
    from .evaluator import run_eval_from_hosted

    async def document_task(inputs: DocumentInput) -> DocumentOutput:
        if inputs.workflow == "task":
            deps = TaskDependencies(
                feature_description=_GRAPH_FIXTURES["feature_description"],
                project_id=inputs.project_id,
                codebase_map=inputs.files,
                open_violations=list(_GRAPH_FIXTURES["open_violations"]),
                prior_decisions=inputs.decisions,
            )
            task_result = await task_agent.run(inputs.prompt, deps=deps)
            return DocumentOutput(text=_render_task_report(task_result.output))

        decision_deps = DecisionDependencies(
            project_id=inputs.project_id,
            package_path="eval-fixture",
            decisions=inputs.decisions,
            extra_file_context=format_preloaded_files(
                cast(list[dict[str, str]], inputs.files)
            ),
        )
        decision_result = await decision_agent.run(inputs.prompt, deps=decision_deps)
        return DocumentOutput(text=_render_decision_report(decision_result.output))

    await run_eval_from_hosted(
        "document-golden-set",
        document_task,
        DocumentInput,
        DocumentOutput,
        DocumentMeta,
    )
