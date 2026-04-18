#!/usr/bin/env python3
"""Read-only Jina integration tools."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ...services.jina_embedder import (
    JinaConfigurationError,
    get_jina_embedder,
)

mcp = FastMCP("integrations", instructions="Read-only Jina issue fetch and ticket-to-code linking tools.")

_TAG = {"namespace:integrations"}


@mcp.tool(tags=_TAG)
async def jina_fetch_issues(
    jql: Annotated[
        str | None,
        Field(description="Optional JQL query. Defaults to the configured project key if omitted."),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of issues to fetch.", ge=1, le=100),
    ] = 25,
    project_id: Annotated[
        str | None,
        Field(description="Optional project node ID used to link imported Jina issues into the graph."),
    ] = None,
) -> dict:
    """Fetch Jina issues over the read-only Jina search API and persist them in the graph."""
    embedder = get_jina_embedder()
    try:
        issues = await embedder.fetch_issues(jql=jql, limit=limit)
        await embedder.sync_issues(issues, project_id=project_id)
    except JinaConfigurationError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to fetch Jina issues: {exc}"}

    return {
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "count": len(issues),
        "read_only": True,
    }


@mcp.tool(tags=_TAG)
async def jina_find_code_for_ticket(
    issue_key: Annotated[str, Field(description="Jina issue key, for example MEM-42.")],
    root_path: Annotated[
        str | None,
        Field(description="Optional repository root. Defaults to the linked project repo_path or the current working directory."),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(description="Optional project node ID used for graph links and repo_path resolution."),
    ] = None,
    limit: Annotated[int, Field(description="Maximum number of code matches to return.", ge=1, le=20)] = 5,
    threshold: Annotated[
        float | None,
        Field(description="Optional semantic match threshold override between 0 and 1.", ge=0.0, le=1.0),
    ] = None,
    force_refresh: Annotated[
        bool,
        Field(description="When true, rebuild the in-memory code index instead of reusing the active cache."),
    ] = False,
) -> dict:
    """Fetch a Jina issue and find the most relevant code files for it."""
    embedder = get_jina_embedder()
    try:
        issue = await embedder.fetch_issue(issue_key)
        if issue is None:
            return {"error": f"Jina issue {issue_key!r} was not found."}
        matches = await embedder.find_code_for_issue(
            issue,
            root_path=root_path,
            project_id=project_id,
            threshold=threshold,
            limit=limit,
            force_refresh=force_refresh,
        )
    except JinaConfigurationError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to link Jina issue to code: {exc}"}

    return {
        "issue": issue.model_dump(mode="json"),
        "matches": [match.model_dump(mode="json") for match in matches],
        "count": len(matches),
    }


@mcp.tool(tags=_TAG)
async def jina_find_tickets_for_file(
    file_path: Annotated[str, Field(description="File path to look up tickets for. Relative paths resolve against root_path or the project repo_path.")],
    root_path: Annotated[
        str | None,
        Field(description="Optional repository root. Defaults to the linked project repo_path or the current working directory."),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(description="Optional project node ID used for graph scoping and repo_path resolution."),
    ] = None,
    limit: Annotated[int, Field(description="Maximum number of Jina matches to return.", ge=1, le=20)] = 5,
    threshold: Annotated[
        float | None,
        Field(description="Optional semantic match threshold override between 0 and 1.", ge=0.0, le=1.0),
    ] = None,
    include_resolved: Annotated[
        bool,
        Field(description="Include closed or resolved Jina issues in the result set."),
    ] = True,
) -> dict:
    """Find persisted Jina issues related to a specific file."""
    embedder = get_jina_embedder()
    try:
        matches = await embedder.find_tickets_for_file(
            file_path,
            root_path=root_path,
            project_id=project_id,
            threshold=threshold,
            limit=limit,
            include_resolved=include_resolved,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to find Jina issues for file: {exc}"}

    return {
        "file_path": file_path,
        "matches": [match.model_dump(mode="json") for match in matches],
        "count": len(matches),
    }