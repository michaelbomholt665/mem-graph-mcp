"""Internal server metadata and discovery helpers."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from ..app.registry import all_agents
from .constants import (
    DEPRECATED_NAMESPACES,
    LAZY_NAMESPACES,
    SERVER_API_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SERVER_WEBSITE,
)
from ..providers.skills.registry import all_skills, task_type_map

logger = logging.getLogger(__name__)


def server_info_payload() -> dict[str, str]:
    return {
        "name": SERVER_NAME,
        "version": SERVER_VERSION,
        "api_version": SERVER_API_VERSION,
        "website": SERVER_WEBSITE,
    }


def get_server_info() -> dict[str, str]:
    """Return stable server metadata for clients and operators."""
    return server_info_payload()


def get_namespace(tool_def: Any) -> str:
    tags = getattr(tool_def, "tags", [])
    for tag in tags or []:
        if tag.startswith("namespace:"):
            return tag.replace("namespace:", "")
    return "core"


async def catalog_tools(mcp: FastMCP) -> list[Any]:
    """Return the raw tool catalog across mounted providers."""
    tools_by_name: dict[str, Any] = {}
    for provider in mcp.providers:
        if provider.__class__.__name__ == "SkillsDirectoryProvider":
            continue
        try:
            for tool_def in await provider.list_tools():
                tools_by_name[tool_def.name] = tool_def
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "catalog_tool_provider_failed provider=%s error=%s",
                provider,
                exc,
            )
    return [tools_by_name[name] for name in sorted(tools_by_name)]


def list_agents() -> list[dict[str, object]]:
    """List registered sub-agents with their categories and task types."""
    return [agent.to_dict() for agent in all_agents()]


def list_task_types() -> dict[str, list[str]]:
    """List public task categories and task types for sub-agent dispatch."""
    return task_type_map()


async def system_inspect(
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Summarize tools, prompts, resources, agents, and task types in one call."""
    if ctx is None:
        return {"error": "Context is required for system inspection."}

    tools = await catalog_tools(ctx.fastmcp)
    prompts = await ctx.fastmcp.list_prompts()
    resources = await ctx.fastmcp.list_resources()
    templates = await ctx.fastmcp.list_resource_templates()
    agents = all_agents()
    task_types = task_type_map()
    skills = all_skills()

    return {
        "orientation": (
            "Start with search_tools(query='...') to find capabilities, then "
            "use call_tool or direct tool calls as needed."
        ),
        "tools": {
            "count": len(tools),
            "examples": [tool.name for tool in tools[:5]],
        },
        "prompts": {
            "count": len(prompts),
            "examples": [prompt.name for prompt in prompts[:5]],
        },
        "resources": {
            "count": len(resources) + len(templates),
            "examples": [str(resource.uri) for resource in resources[:3]]
            + [template.uri_template for template in templates[:2]],
        },
        "agents": {
            "count": len(agents),
            "examples": [agent.name for agent in agents[:5]],
        },
        "task_types": {
            "status": (
                "pending — skill workflow under construction"
                if not task_types
                else "available"
            ),
            "categories": task_types,
        },
        "skills": {
            "count": len(skills),
            "status": "registry scaffolded; no skills registered yet"
            if not skills
            else "registered",
        },
        "lazy_namespaces": sorted(LAZY_NAMESPACES),
    }


async def tools_activate(
    namespace: Annotated[
        str,
        Field(
            description=(
                "Namespace to activate for this session: memory, work, notes, "
                "audit, filesystem, background, graph, integrations, or code."
            )
        ),
    ],
    ctx: Context,
) -> dict[str, Any]:
    """Enable a lazy namespace for the current session."""
    if namespace in DEPRECATED_NAMESPACES:
        canonical = DEPRECATED_NAMESPACES[namespace]
        await ctx.enable_components(tags={f"namespace:{canonical}"}, components={"tool"})
        return {
            "activated": canonical,
            "status": "ok",
            "deprecation_notice": (
                f"Namespace '{namespace}' has been consolidated into '{canonical}'. "
                f"Please use tools_activate(namespace='{canonical}') in future."
            ),
        }

    if namespace not in LAZY_NAMESPACES:
        return {
            "error": (
                f"Unknown namespace {namespace!r}. "
                f"Choose from: {sorted(LAZY_NAMESPACES)}"
            )
        }
    await ctx.enable_components(tags={f"namespace:{namespace}"}, components={"tool"})
    await ctx.info(f"Activated namespace '{namespace}' for session.")
    logger.info("Activated namespace '%s' for session.", namespace)
    return {"activated": namespace, "status": "ok"}


def register_tools(mcp: FastMCP) -> None:
    mcp.tool()(get_server_info)
    mcp.tool()(list_agents)
    mcp.tool()(list_task_types)
    mcp.tool()(system_inspect)
    mcp.tool()(tools_activate)
