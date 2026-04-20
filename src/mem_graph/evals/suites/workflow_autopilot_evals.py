"""Autopilot workflow eval suite."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from pydantic_evals import Case, Dataset

from ...agents.orchestrator_graph import autopilot_graph_run
from ...models.agent_outputs import (
    FilePatch,
    FixerReport,
    SentryReport,
    TestCaseProposal,
)
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text


@dataclass
class AutopilotWorkflowInput:
    prompt: str
    case_id: str


_TARGET_FILE = "target.py"


_FIXTURE_OUTPUTS = {
    "workflow-autopilot-clean-pass": "success=True validation_status=approved retry_count=0 notes=1 spans=orchestrator.context_gather,orchestrator.memory_sync",
    "workflow-autopilot-guard-rejects": "success=False validation_status=rejected retry_count=1 notes=1 spans=orchestrator.context_gather,orchestrator.memory_sync",
}


WORKFLOW_AUTOPILOT_EVAL_SUITE = EvalSuite(
    suite_name="workflow_autopilot",
    agent_name="autopilot_graph",
    description="Autopilot workflow coverage for clean approvals, guard rejection, note sync, and span ordering.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=1,
    max_case_concurrency=2,
    cases=[
        EvalCase(
            case_id="workflow-autopilot-clean-pass",
            description="A clean validation pass should finish successfully, sync a note, and record the expected spans.",
            prompt="Run the autopilot workflow where the guard passes immediately.",
            expected_keywords=[
                "success=True",
                "approved",
                "orchestrator.context_gather",
                "orchestrator.memory_sync",
            ],
            tags=["workflow", "autopilot"],
        ),
        EvalCase(
            case_id="workflow-autopilot-guard-rejects",
            description="A failing guard should reject the run, increment retry count, and still sync a final note.",
            prompt="Run the autopilot workflow where the guard rejects the patch.",
            expected_keywords=["success=False", "rejected", "retry_count=1", "notes=1"],
            tags=["workflow", "guard"],
        ),
    ],
)


def _render_autopilot_state(state, span_names: list[str], note_count: int) -> str:
    return (
        f"success={state.success} validation_status={state.validation_status} retry_count={state.retry_count} "
        f"notes={note_count} spans={','.join(span_names)}"
    )


def _synthetic_fixer_report(patches: list[FilePatch]) -> FixerReport:
    return FixerReport(
        patches=patches,
        unresolved_violations=[],
        summary="Applied focused exception-handling fixes.",
        tier_used="standard",
    )


async def _run_autopilot_case(case_id: str) -> str:
    span_names: list[str] = []
    notes: list[tuple[str, str]] = []

    class DummySpan:
        def set_attribute(self, name: str, value: object) -> None:
            del name, value

    @contextmanager
    def fake_traced_span(name: str, attributes: dict[str, object] | None = None):
        del attributes
        span_names.append(name)
        yield DummySpan()

    class FakeGraphContextService:
        async def query_violations(self, project_id: str):
            del project_id
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    rule="CWE-703",
                    file_path=_TARGET_FILE,
                    description="Bare except swallows failures.",
                )
            ]

        async def query_decisions(self, project_id: str):
            del project_id
            await asyncio.sleep(0)
            return [
                SimpleNamespace(
                    title="Prefer explicit exception handling",
                    rationale="Do not swallow runtime failures.",
                )
            ]

        async def query_map(self, project_id: str) -> str:
            del project_id
            await asyncio.sleep(0)
            return f"{_TARGET_FILE} is part of the memory ingestion surface."

    async def fake_sentry_run(prompt: str, deps) -> SimpleNamespace:
        del prompt, deps
        await asyncio.sleep(0)
        return SimpleNamespace(
            output=SentryReport(
                test_cases=[
                    TestCaseProposal(
                        file_path=_TARGET_FILE,
                        test_name="test_target_raises_runtime_error",
                        failing_assertion="pytest.raises(RuntimeError)",
                        rationale="The regression should fail before the fix lands.",
                    )
                ],
                summary="One deterministic failing regression test.",
                framework="pytest",
            )
        )

    async def fake_fixer_run(prompt: str, deps) -> SimpleNamespace:
        del prompt
        await asyncio.sleep(0)
        patches = [
            FilePatch(
                file_path=file_path,
                original_snippet=content,
                proposed_snippet=content.replace(
                    "except:\n        pass",
                    "except Exception as exc:\n        raise RuntimeError('boom') from exc",
                ),
                violation_ids=["CWE-703"],
                rationale="Replace the swallowed exception with an explicit error.",
            )
            for file_path, content in deps.file_contents.items()
        ]
        return SimpleNamespace(output=_synthetic_fixer_report(patches))

    async def fake_scribe_run(prompt: str, deps) -> SimpleNamespace:
        del prompt
        await asyncio.sleep(0)
        styled_patches = [
            SimpleNamespace(file_path=file_path, styled_content=content)
            for file_path, content in deps.file_contents.items()
        ]
        return SimpleNamespace(output=SimpleNamespace(styled_patches=styled_patches))

    async def fake_quality_gate() -> tuple[bool, list[str], str]:
        await asyncio.sleep(0)
        if case_id == "workflow-autopilot-clean-pass":
            return True, [], "ruff ok\nmypy ok"
        return False, ["ruff: synthetic failure"], "ruff failed"

    def fake_write_note(project_id: str, content: str) -> None:
        notes.append((project_id, content))

    with TemporaryDirectory() as tmp_dir, ExitStack() as stack:
        file_path = Path(tmp_dir) / _TARGET_FILE
        file_path.write_text(
            "def work():\n    try:\n        return 1\n    except:\n        pass\n",
            encoding="utf-8",
        )

        stack.enter_context(
            patch(
                "mem_graph.agents.orchestrator_graph.traced_span", new=fake_traced_span
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.services.graph_context_service.GraphContextService",
                new=FakeGraphContextService,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.validate.sentry_agent.sentry_agent.run",
                new=fake_sentry_run,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.fix.fixer_agent.fixer_agent.run",
                new=fake_fixer_run,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.document.scribe_agent.scribe_agent.run",
                new=fake_scribe_run,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.orchestrator_graph._state_run_quality_gate",
                new=fake_quality_gate,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.orchestrator_graph._state_write_note",
                new=fake_write_note,
            )
        )
        stack.enter_context(
            patch(
                "mem_graph.agents.orchestrator_graph._state_read_manifests",
                new=lambda: {"pyproject.toml": "[tool.ruff]\n"},
            )
        )

        state = await autopilot_graph_run(
            language="python",
            target_files=[str(file_path)],
            project_id="proj-evals",
            max_retries=1,
        )

    return _render_autopilot_state(state, span_names, len(notes))


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(
        _FIXTURE_OUTPUTS,
        case.case_id,
        suite_name="workflow_autopilot",
    )


async def _run_live(case: EvalCase) -> str:
    return await _run_autopilot_case(case.case_id)


def build_workflow_autopilot_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=WORKFLOW_AUTOPILOT_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_workflow_autopilot_dataset() -> Dataset[
    AutopilotWorkflowInput,
    HostedTextOutput,
    HostedTextMeta,
]:
    cases: list[Case[AutopilotWorkflowInput, HostedTextOutput, HostedTextMeta]] = []
    for case in WORKFLOW_AUTOPILOT_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=AutopilotWorkflowInput(prompt=case.prompt, case_id=case.case_id),
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(
                    case, WORKFLOW_AUTOPILOT_EVAL_SUITE.default_scorer
                ),
                evaluators=(HostedTextScorer(),),
            )
        )
    return Dataset[AutopilotWorkflowInput, HostedTextOutput, HostedTextMeta](
        name="workflow-autopilot-golden-set",
        cases=cases,
    )


def push_workflow_autopilot_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_workflow_autopilot_dataset(),
            description=WORKFLOW_AUTOPILOT_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_workflow_autopilot_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def workflow_task(inputs: AutopilotWorkflowInput) -> HostedTextOutput:
        return HostedTextOutput(text=await _run_autopilot_case(inputs.case_id))

    await run_eval_from_hosted(
        "workflow-autopilot-golden-set",
        workflow_task,
        AutopilotWorkflowInput,
        HostedTextOutput,
        HostedTextMeta,
    )


__all__ = [
    "WORKFLOW_AUTOPILOT_EVAL_SUITE",
    "build_workflow_autopilot_binding",
    "build_workflow_autopilot_dataset",
    "push_workflow_autopilot_dataset",
    "run_workflow_autopilot_eval",
]
