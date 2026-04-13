from __future__ import annotations

import json

from .graph_queries import get_graph_snapshot, get_node_details, load_node_styles, mcp


@mcp.resource(
    "graph://snapshot",
    description="Read the current dashboard graph snapshot as JSON.",
    mime_type="application/json",
)
async def graph_snapshot_resource() -> str:
    snapshot = await get_graph_snapshot()
    return snapshot.model_dump_json()


@mcp.resource(
    "graph://nodes/{node_id}",
    description="Read a single dashboard node and its relationships as JSON.",
    mime_type="application/json",
)
async def graph_node_resource(node_id: str) -> str:
    details = await get_node_details(node_id)
    if hasattr(details, "model_dump_json"):
        return details.model_dump_json()
    return json.dumps(details)


@mcp.resource(
    "graph://styles",
    description="Read the dashboard node-style metadata as JSON.",
    mime_type="application/json",
)
async def graph_styles_resource() -> str:
    return json.dumps({"styles": load_node_styles()})