#!/usr/bin/env python3
import asyncio
import os

os.environ.setdefault("OPENAI_API_KEY", "test")

from typing import Any, cast

import pytest
from pydantic_ai import messages
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage, UsageLimits

from mem_graph.agents.audit.audit_agent import (
    AuditDependencies,
    audit_agent,
)
from mem_graph.agents.audit.audit_agent import (
    process_batch as audit_process_batch,
)
from mem_graph.agents.document.decision_agent import (
    DecisionDependencies,
    decision_agent,
)
from mem_graph.agents.document.decision_agent import (
    process_batch as decision_process_batch,
)
from mem_graph.agents.map.chat_agent import (
    ChatDependencies,
    chat_agent,
    chat_dump_message_history,
    chat_load_message_history,
    chat_traverse_relationship,
    run_chat_turn,
)
from mem_graph.agents.map.map_agent import (
    MapDependencies,
    map_agent,
)
from mem_graph.agents.map.map_agent import (
    process_batch as map_process_batch,
)
from mem_graph.agents.orchestrator_agent import (
    BatchFileContent,
    OrchestratorDependencies,
    _run_map_batch,
)
from mem_graph.config import config_build_orchestrator_usage_limits


class MockContext:
    def __init__(self, deps: Any):
        self.deps = deps


def _function_tool_names(model: TestModel) -> set[str]:
    params = cast(Any, model.last_model_request_parameters)
    assert params is not None
    return {tool.name for tool in params.function_tools}


@pytest.mark.asyncio
async def test_audit_preloaded_mode_hides_agent_local_tools() -> None:
    standalone_model = TestModel(call_tools=[])
    preloaded_model = TestModel(call_tools=[])

    with audit_agent.override(model=standalone_model):
        await audit_agent.run(
            "Audit the package.",
            deps=AuditDependencies(package_path="/tmp/project"),
        )

    with audit_agent.override(model=preloaded_model):
        await audit_agent.run(
            "Audit the provided files.",
            deps=AuditDependencies(
                package_path="/tmp/project",
                mode="preloaded",
                extra_file_context="### app.py\nprint('hello')\n",
            ),
        )

    standalone_tools = _function_tool_names(standalone_model)
    preloaded_tools = _function_tool_names(preloaded_model)

    assert {"list_files", "process_batch", "finalize_report"} <= standalone_tools
    assert preloaded_tools == set()


@pytest.mark.asyncio
async def test_map_preloaded_mode_hides_agent_local_tools() -> None:
    standalone_model = TestModel(call_tools=[])
    preloaded_model = TestModel(call_tools=[])

    with map_agent.override(model=standalone_model):
        await map_agent.run(
            "Map the package.",
            deps=MapDependencies(package_path="/tmp/project"),
        )

    with map_agent.override(model=preloaded_model):
        await map_agent.run(
            "Map the provided files.",
            deps=MapDependencies(
                package_path="/tmp/project",
                extra_file_context="### app.py\nprint('hello')\n",
            ),
        )

    standalone_tools = _function_tool_names(standalone_model)
    preloaded_tools = _function_tool_names(preloaded_model)

    assert {"list_files", "process_batch", "finalize_map"} <= standalone_tools
    assert preloaded_tools == set()


@pytest.mark.asyncio
async def test_decision_preloaded_mode_hides_agent_local_tools() -> None:
    standalone_model = TestModel(call_tools=[])
    preloaded_model = TestModel(call_tools=[])

    with decision_agent.override(model=standalone_model):
        await decision_agent.run(
            "Review the package decisions.",
            deps=DecisionDependencies(project_id="proj", package_path="/tmp/project"),
        )

    with decision_agent.override(model=preloaded_model):
        await decision_agent.run(
            "Review the provided files.",
            deps=DecisionDependencies(
                project_id="proj",
                package_path="/tmp/project",
                extra_file_context="### app.py\nprint('hello')\n",
            ),
        )

    standalone_tools = _function_tool_names(standalone_model)
    preloaded_tools = _function_tool_names(preloaded_model)

    assert {"list_files", "process_batch", "finalize_review"} <= standalone_tools
    assert preloaded_tools == set()


@pytest.mark.asyncio
async def test_oversized_batch_requests_raise_model_retry() -> None:
    oversized_batch = [f"file_{index}.py" for index in range(6)]

    audit_ctx = cast(
        RunContext[AuditDependencies],
        MockContext(AuditDependencies(package_path="/tmp/project")),
    )
    with pytest.raises(ModelRetry):
        await audit_process_batch(audit_ctx, oversized_batch, [])

    map_ctx = cast(
        RunContext[MapDependencies],
        MockContext(MapDependencies(package_path="/tmp/project")),
    )
    with pytest.raises(ModelRetry):
        await map_process_batch(map_ctx, oversized_batch, [], [])

    decision_ctx = cast(
        RunContext[DecisionDependencies],
        MockContext(
            DecisionDependencies(project_id="proj", package_path="/tmp/project")
        ),
    )
    with pytest.raises(ModelRetry):
        await decision_process_batch(decision_ctx, oversized_batch, [])


@pytest.mark.asyncio
async def test_chat_toolset_registers_retrieval_tools() -> None:
    model = TestModel(call_tools=[])

    with chat_agent.override(model=model):
        await chat_agent.run(
            "Why do we keep memory entries?",
            deps=ChatDependencies(project_id="proj"),
        )

    tool_names = _function_tool_names(model)
    assert {
        "chat_recall_memories",
        "chat_search_violations",
        "chat_search_decisions",
        "chat_traverse_relationship",
    } <= tool_names


@pytest.mark.asyncio
async def test_chat_turn_round_trips_message_history_with_function_model() -> None:
    seen_message_kinds: list[list[str]] = []

    async def fake_model(message_history, agent_info):
        await asyncio.sleep(0)
        seen_message_kinds.append([message.kind for message in message_history])
        output_tool = agent_info.output_tools[0]
        answer_text = "first-turn" if len(seen_message_kinds) == 1 else "second-turn"
        return messages.ModelResponse(
            parts=[
                messages.ToolCallPart(
                    tool_name=output_tool.name,
                    args={
                        "answer": answer_text,
                        "sources": ["M-001"],
                        "confidence": 0.9,
                        "follow_up_hints": ["Ask another question."],
                    },
                )
            ]
        )

    deps = ChatDependencies(project_id="proj")
    usage_limits = UsageLimits(request_limit=4, tool_calls_limit=8)

    with chat_agent.override(model=FunctionModel(fake_model)):
        first_turn = await run_chat_turn(
            "What changed?",
            deps=deps,
            usage_limits=usage_limits,
        )
        second_turn = await run_chat_turn(
            "Why did it change?",
            deps=deps,
            message_history_json=first_turn.message_history_json,
            usage_limits=usage_limits,
        )

    restored_history = chat_load_message_history(first_turn.message_history_json)

    assert first_turn.answer.answer == "first-turn"
    assert second_turn.answer.answer == "second-turn"
    assert restored_history is not None
    assert first_turn.message_count == len(restored_history)
    assert (
        chat_dump_message_history(restored_history) == first_turn.message_history_json
    )
    assert seen_message_kinds[0] == ["request"]
    assert len(seen_message_kinds[1]) > len(seen_message_kinds[0])


@pytest.mark.asyncio
async def test_chat_traverse_relationship_rejects_invalid_direction() -> None:
    ctx = cast(
        RunContext[ChatDependencies],
        MockContext(ChatDependencies(project_id="proj")),
    )

    with pytest.raises(ModelRetry):
        await chat_traverse_relationship(
            ctx,
            node_id="D-001",
            node_type="Decision",
            relationship="SUPERSEDES",
            direction="sideways",
        )


def test_orchestrator_usage_limit_budget_scales_with_batches() -> None:
    limits = config_build_orchestrator_usage_limits(total_batches=3)

    assert limits.request_limit == 10
    assert limits.tool_calls_limit == 8


@pytest.mark.asyncio
async def test_orchestrator_delegate_receives_usage_limits(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run(prompt: str, *, deps, usage=None, usage_limits=None):
        await asyncio.sleep(0)
        captured["prompt"] = prompt
        captured["deps"] = deps
        captured["usage"] = usage
        captured["usage_limits"] = usage_limits

        class Result:
            output = {"status": "ok"}

        return Result()

    monkeypatch.setattr(map_agent, "run", fake_run)

    limits = UsageLimits(request_limit=7, tool_calls_limit=11)
    deps = OrchestratorDependencies(
        package_path="/tmp/project",
        project_id="proj",
        subagent_name="map",
        usage_limits=limits,
    )

    result = await _run_map_batch(
        deps,
        [BatchFileContent(path="app.py", content="print('hello')\n", truncated=False)],
        RunUsage(),
    )

    assert result == {"status": "ok"}
    assert isinstance(captured["usage"], RunUsage)
    assert captured["usage_limits"] is limits
