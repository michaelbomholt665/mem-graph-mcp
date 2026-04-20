"""Managed feature-implementation workflow eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic_evals import Case, Dataset

from ...agents.workflow_graph import run_managed_workflow
from ...models.agent_outputs import WorkflowPlan
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class FeatureWorkflowInput:
    prompt: str
    case_id: str


_FIXTURE_OUTPUTS = {
    "workflow-feature-stage-order": "stages=context_gather,planning,implementation,audit,debug_validation,documentation,context_map_update,memory_bank_sync blockers=0",
    "workflow-feature-scope-boundary": "target_files=2 blockers=0 final_report=Workflow completed",
}


WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE = EvalSuite(
    suite_name="workflow_feature_implementation",
    agent_name="managed_workflow",
    description="Managed workflow coverage for stage order and file-scope discipline.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="workflow-feature-stage-order",
            description="Managed workflow should record its deterministic stage order end to end.",
            prompt="Run the managed feature workflow for a small change.",
            expected_keywords=["context_gather", "implementation", "memory_bank_sync"],
            tags=["workflow", "stages"],
        ),
        EvalCase(
            case_id="workflow-feature-scope-boundary",
            description="Managed workflow should keep work bounded to the target file set.",
            prompt="Run the managed feature workflow over two files and report scope.",
            expected_keywords=["target_files=2", "blockers=0", "Workflow completed"],
            tags=["workflow", "scope"],
        ),
    ],
)


def _render_managed_state(state) -> str:
    stages = ",".join(result.stage for result in state.stage_results)
    return (
        f"stages={stages} target_files={len(state.target_files)} blockers={len(state.blockers)} "
        f"final_report={state.final_report}"
    )


async def _run_managed_feature_workflow() -> str:
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        file_a = root / "memory.py"
        file_b = root / "telemetry.py"
        file_a.write_text(
            "def store_memory(value):\n    return value\n", encoding="utf-8"
        )
        file_b.write_text("def span(name):\n    return name\n", encoding="utf-8")

        plan = WorkflowPlan(
            objective="Implement a small feature safely.",
            project_id="proj-evals",
            target_files=[str(file_a), str(file_b)],
            max_retries=1,
        )
        state = await run_managed_workflow(plan, execute_agents=False)
        return _render_managed_state(state)


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(
        _FIXTURE_OUTPUTS,
        case.case_id,
        suite_name="workflow_feature_implementation",
    )


async def _run_live(case: EvalCase) -> str:
    del case
    return await _run_managed_feature_workflow()


def build_workflow_feature_implementation_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_workflow_feature_implementation_dataset() -> Dataset[
    FeatureWorkflowInput,
    HostedTextOutput,
    HostedTextMeta,
]:
    cases: list[Case[FeatureWorkflowInput, HostedTextOutput, HostedTextMeta]] = []
    for case in WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=FeatureWorkflowInput(prompt=case.prompt, case_id=case.case_id),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(
                    case,
                    WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE.default_scorer,
                ),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[FeatureWorkflowInput, HostedTextOutput, HostedTextMeta](
        name="workflow-feature-implementation-golden-set",
        cases=cases,
    )


def push_workflow_feature_implementation_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_workflow_feature_implementation_dataset(),
            description=WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_workflow_feature_implementation_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def workflow_task(inputs: FeatureWorkflowInput) -> HostedTextOutput:
        del inputs
        return HostedTextOutput(text=await _run_managed_feature_workflow())

    await run_eval_from_hosted(
        "workflow-feature-implementation-golden-set",
        workflow_task,
        FeatureWorkflowInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "WORKFLOW_FEATURE_IMPLEMENTATION_EVAL_SUITE",
    "build_workflow_feature_implementation_binding",
    "build_workflow_feature_implementation_dataset",
    "push_workflow_feature_implementation_dataset",
    "run_workflow_feature_implementation_eval",
]
