"""Router agent eval suite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from pydantic_evals import Case, Dataset

from ...agents.router_agent import RouterDependencies, router_agent
from ...models.evals import EvalCase, EvalMode, EvalSuite, SuiteBinding
from ..fixtures import fixture_output_for
from ..scorers import HostedTextScorer
from .common import HostedTextMeta, HostedTextOutput, build_text_meta, expected_text

WorkflowModeValue = Literal["route_only", "subagent_workflow"]
_DB_PATH = "src/mem_graph/db.py"
_MEMORY_TOOL_PATH = "src/mem_graph/tools/memory/memory.py"
_OTEL_SETUP_PATH = "src/mem_graph/observability/otel_setup.py"


@dataclass
class RouterInput:
    prompt: str
    project_id: str
    file_paths: list[str]
    workflow_mode: WorkflowModeValue
    context_violations: list[str]
    context_decisions: list[str]


_FIXTURE_OUTPUTS = {
    "router-single-file-fix": "tier=micro mode=route_only intent=fix subtasks=fixer stages=none",
    "router-large-audit": "tier=autopilot mode=route_only intent=audit subtasks=audit,map stages=none",
    "router-workflow-plan": "tier=standard mode=subagent_workflow intent=document subtasks=router stages=planning,implementation,audit",
}


ROUTER_EVAL_SUITE = EvalSuite(
    suite_name="router",
    agent_name="router",
    description="Router coverage for tier selection, orchestration mode, and workflow planning.",
    default_scorer="keywords",
    pass_threshold=0.67,
    default_runs=2,
    max_case_concurrency=3,
    cases=[
        EvalCase(
            case_id="router-single-file-fix",
            description="Single-file remediation should stay route-only and favor a small tier.",
            prompt="Fix a bare except bug in src/mem_graph/db.py.",
            expected_keywords=["micro", "route_only", "fix"],
            tags=["routing", "tiering"],
            metadata={
                "file_paths": [_DB_PATH],
                "workflow_mode": "route_only",
            },
        ),
        EvalCase(
            case_id="router-large-audit",
            description="Repo-wide audits should route to orchestration instead of a tiny single-agent pass.",
            prompt="Audit the entire codebase for security issues and summarise the riskiest areas.",
            expected_keywords=["autopilot", "route_only", "audit"],
            tags=["routing", "audit"],
            metadata={
                "file_paths": [
                    "src/mem_graph/server.py",
                    _DB_PATH,
                    _MEMORY_TOOL_PATH,
                    _OTEL_SETUP_PATH,
                    "src/mem_graph/evals/evaluator.py",
                    "src/mem_graph/agents/orchestrator_graph.py",
                    "src/mem_graph/workflows/runtime/orchestrator_runtime.py",
                    "src/mem_graph/tools/agents/orchestrator.py",
                    "src/mem_graph/agents/router_agent.py",
                    "src/mem_graph/models/agent_outputs.py",
                ],
                "workflow_mode": "route_only",
            },
        ),
        EvalCase(
            case_id="router-workflow-plan",
            description="Explicit workflow requests should emit a managed workflow plan.",
            prompt="Plan a full staged workflow for documenting and implementing the memory observability feature.",
            expected_keywords=["subagent_workflow", "planning", "implementation"],
            tags=["routing", "workflow"],
            metadata={
                "file_paths": [
                    _MEMORY_TOOL_PATH,
                    _OTEL_SETUP_PATH,
                ],
                "workflow_mode": "subagent_workflow",
                "context_violations": [
                    "observability:missing-span src/mem_graph/tools/memory/memory.py"
                ],
                "context_decisions": ["D-001 prefer redacted observability metadata"],
            },
        ),
    ],
)


def _render_router_decision(output) -> str:
    stage_names = []
    if output.workflow_plan is not None:
        stage_names = [stage.name for stage in output.workflow_plan.required_stages]
    agents = [task.agent for task in output.sub_tasks]
    return (
        f"tier={output.tier.value.lower()} mode={output.workflow_mode} intent={output.intent} "
        f"subtasks={','.join(agents) or 'none'} stages={','.join(stage_names) or 'none'}"
    )


async def _run_fixture(case: EvalCase) -> str:
    await asyncio.sleep(0)
    return fixture_output_for(_FIXTURE_OUTPUTS, case.case_id, suite_name="router")


async def _run_live(case: EvalCase) -> str:
    inputs = _ROUTER_INPUTS[case.case_id]
    deps = RouterDependencies(
        project_id=inputs.project_id,
        request=inputs.prompt,
        file_paths=inputs.file_paths,
        context_violations=inputs.context_violations,
        context_decisions=inputs.context_decisions,
        workflow_mode=inputs.workflow_mode,
        project_root=".",
    )
    result = await router_agent.run(case.prompt, deps=deps)
    return _render_router_decision(result.output)


def build_router_binding(mode: EvalMode) -> SuiteBinding:
    return SuiteBinding(
        suite=ROUTER_EVAL_SUITE,
        runner=_run_fixture if mode == "fixture" else _run_live,
    )


def build_router_dataset() -> Dataset[RouterInput, HostedTextOutput, HostedTextMeta]:
    cases: list[Case[RouterInput, HostedTextOutput, HostedTextMeta]] = []
    for case in ROUTER_EVAL_SUITE.cases:
        cases.append(
            Case(
                name=case.case_id,
                inputs=_ROUTER_INPUTS[case.case_id],
                expected_output=HostedTextOutput(text=expected_text(case)),
                metadata=build_text_meta(case, ROUTER_EVAL_SUITE.default_scorer),
                evaluators=(HostedTextScorer(),),
            )
        )

    return Dataset[RouterInput, HostedTextOutput, HostedTextMeta](
        name="router-golden-set",
        cases=cases,
    )


def push_router_dataset() -> dict[str, object]:
    from ..logfire_client import get_client

    with get_client() as client:
        result = client.push_dataset(
            build_router_dataset(),
            description=ROUTER_EVAL_SUITE.description,
        )
        print(f"Pushed: {result['name']} - {result['id']}")
        return result


async def run_router_eval() -> None:
    from ..evaluator import run_eval_from_hosted

    async def router_task(inputs: RouterInput) -> HostedTextOutput:
        deps = RouterDependencies(
            project_id=inputs.project_id,
            request=inputs.prompt,
            file_paths=inputs.file_paths,
            context_violations=inputs.context_violations,
            context_decisions=inputs.context_decisions,
            workflow_mode=inputs.workflow_mode,
            project_root=".",
        )
        result = await router_agent.run(inputs.prompt, deps=deps)
        return HostedTextOutput(text=_render_router_decision(result.output))

    await run_eval_from_hosted(
        "router-golden-set",
        router_task,
        RouterInput,
        HostedTextOutput,
        HostedTextMeta,
    )


_ROUTER_INPUTS: dict[str, RouterInput] = {
    "router-single-file-fix": RouterInput(
        prompt="Fix a bare except bug in src/mem_graph/db.py.",
        project_id="proj-evals",
        file_paths=[_DB_PATH],
        workflow_mode="route_only",
        context_violations=[],
        context_decisions=[],
    ),
    "router-large-audit": RouterInput(
        prompt="Audit the entire codebase for security issues and summarise the riskiest areas.",
        project_id="proj-evals",
        file_paths=[
            "src/mem_graph/server.py",
            _DB_PATH,
            _MEMORY_TOOL_PATH,
            _OTEL_SETUP_PATH,
            "src/mem_graph/evals/evaluator.py",
            "src/mem_graph/agents/orchestrator_graph.py",
            "src/mem_graph/workflows/runtime/orchestrator_runtime.py",
            "src/mem_graph/tools/agents/orchestrator.py",
            "src/mem_graph/agents/router_agent.py",
            "src/mem_graph/models/agent_outputs.py",
        ],
        workflow_mode="route_only",
        context_violations=[],
        context_decisions=[],
    ),
    "router-workflow-plan": RouterInput(
        prompt="Plan a full staged workflow for documenting and implementing the memory observability feature.",
        project_id="proj-evals",
        file_paths=[
            _MEMORY_TOOL_PATH,
            _OTEL_SETUP_PATH,
        ],
        workflow_mode="subagent_workflow",
        context_violations=[
            "observability:missing-span src/mem_graph/tools/memory/memory.py"
        ],
        context_decisions=["D-001 prefer redacted observability metadata"],
    ),
}


__all__ = [
    "ROUTER_EVAL_SUITE",
    "build_router_binding",
    "build_router_dataset",
    "push_router_dataset",
    "run_router_eval",
]
