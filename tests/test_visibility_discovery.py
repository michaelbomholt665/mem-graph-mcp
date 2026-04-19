from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_list_tools_pins_discovery_surface():
    from mem_graph import server as server_mod

    tools = await server_mod.mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "list_agents",
        "list_task_types",
        "system_inspect",
        "search_tools",
        "call_tool",
    ]


@pytest.mark.asyncio
async def test_list_agents_uses_registered_metadata():
    from mem_graph.app.tools import list_agents

    agents = list_agents()
    tool_names = {agent["tool"] for agent in agents}

    assert {
        "audit_package",
        "map_codebase",
        "triage_violations",
        "task_decompose_feature",
        "decision_review",
        "generate_diagram",
        "autopilot_remediate",
        "orchestrate_codebase",
        "run_subagent_workflow",
    } <= tool_names
    assert all("categories" in agent and "task_types" in agent for agent in agents)


def test_skill_registry_is_honest_when_empty():
    from mem_graph.providers.skills.registry import all_skills, resolve_skill, task_type_map

    assert all_skills() == []
    assert task_type_map() == {}
    assert resolve_skill("database", "sql_security") is None


@pytest.mark.asyncio
async def test_system_inspect_summarizes_catalog():
    from mem_graph import server as server_mod
    from mem_graph.app.tools import system_inspect

    payload = await system_inspect(SimpleNamespace(fastmcp=server_mod.mcp))

    assert payload["tools"]["count"] >= 60
    assert payload["prompts"]["count"] >= 1
    assert payload["resources"]["count"] >= 1
    assert payload["agents"]["count"] >= 8
    assert payload["task_types"]["categories"] == {}
    assert payload["skills"]["count"] == 0
