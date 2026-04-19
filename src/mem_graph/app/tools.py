"""Internal server metadata and lazy tool discovery tools."""

from __future__ import annotations

import logging
from typing import Annotated, Any, cast

from fastmcp import FastMCP
from fastmcp.server.context import Context
from pydantic import Field

from .constants import (
    DEPRECATED_NAMESPACES,
    LAZY_NAMESPACES,
    SERVER_API_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SERVER_WEBSITE,
)

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


def score_tool(tool_def: Any, query: str) -> int:
    tool_name = tool_def.name
    if tool_name in ["tools_activate", "tools_search"]:
        return 0
    desc = (tool_def.description or "").lower()
    name = tool_name.lower()
    score = 0
    if query in name:
        score += 10
    if query in desc:
        score += 5
    if score == 0:
        query_words = set(query.split())
        name_words = set(name.replace("_", " ").split())
        desc_words = set(desc.split())
        score += len(query_words.intersection(name_words)) * 3
        score += len(query_words.intersection(desc_words))
    return score


def get_namespace(tool_def: Any) -> str:
    tags = getattr(tool_def, "tags", [])
    for tag in tags or []:
        if tag.startswith("namespace:"):
            return tag.replace("namespace:", "")
    return "core"


def register_tools(mcp: FastMCP) -> None:
    mcp.tool()(get_server_info)

    @mcp.tool()
    async def tools_search(
        query: Annotated[
            str, Field(description="Search for tools by functionality, goal, or name")
        ],
    ) -> dict[str, Any]:
        query = query.lower()
        results: list[dict[str, Any]] = []
        all_tools = await mcp.list_tools()
        for tool_def in all_tools:
            score = score_tool(tool_def, query)
            if score > 0:
                results.append(
                    {
                        "tool": tool_def.name,
                        "description": tool_def.description or "No description provided.",
                        "namespace": get_namespace(tool_def),
                        "score": score,
                    }
                )

        results.sort(key=lambda item: cast(int, item["score"]), reverse=True)
        top_results = results[:10]
        if not top_results:
            return {"message": f"No tools found matching {query!r}. Try broader keywords."}

        return {
            "results": [
                {
                    "tool": result["tool"],
                    "purpose": result["description"],
                    "how_to_activate": (
                        f"Call tools_activate(namespace='{result['namespace']}')"
                        if result["namespace"] != "core"
                        else "Already active (core tool)."
                    ),
                }
                for result in top_results
            ],
            "suggestion": (
                "Review the list above and call tools_activate(namespace='...') "
                "for the desired group."
            ),
        }

    @mcp.tool()
    async def tools_activate(
        namespace: Annotated[
            str,
            Field(
                description=(
                    "Namespace to activate for this session. "
                    "One of: memory, work, notes, audit, filesystem, background, graph, integrations."
                )
            ),
        ],
        ctx: Context,
    ) -> dict[str, Any]:
        if namespace in DEPRECATED_NAMESPACES:
            canonical = DEPRECATED_NAMESPACES[namespace]
            await ctx.enable_components(
                tags={f"namespace:{canonical}"}, components={"tool"}
            )
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

