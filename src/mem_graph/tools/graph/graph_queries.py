from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Callable, cast

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from ...db import db_get_connection

mcp = FastMCP("graph", instructions="Knowledge graph exploration tools.")

_NODE_STYLES_PATH = Path(__file__).resolve().parents[2] / "resources" / "node_styles.json"


class NodeSnapshot(BaseModel):
    """A node returned to the lightweight dashboard."""

    id: str
    label: str
    type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeSnapshot(BaseModel):
    """A relationship edge between two snapshot nodes."""

    source: str
    target: str
    type: str
    label: str


class NodeRelationship(BaseModel):
    """A node's related edge and target snapshot."""

    direction: str
    relationship: str
    node: NodeSnapshot


class NodeDetails(BaseModel):
    """Expanded node payload used by the details panel."""

    node: NodeSnapshot
    relationships: list[NodeRelationship] = Field(default_factory=list)


class GraphSnapshot(BaseModel):
    """Top-level payload returned by the graph snapshot API."""

    nodes: list[NodeSnapshot]
    edges: list[EdgeSnapshot]
    available_types: list[str]
    timestamp: str


NodeLoader = Callable[[str | None, int], list[NodeSnapshot]]

_EDGE_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    ("HAS_BACKEND", "Project", "Backend"),
    ("HAS_TASK", "Project", "Task"),
    ("HAS_DECISION", "Project", "Decision"),
    ("HAS_NOTE", "Project", "Note"),
    ("HAS_VIOLATION", "Project", "Violation"),
    ("PROJECT_MEMORY", "Project", "Memory"),
    ("BACKEND_TASK", "Backend", "Task"),
    ("BACKEND_DECISION", "Backend", "Decision"),
    ("BACKEND_SYMBOL", "Backend", "CodeSymbol"),
    ("BACKEND_VIOLATION", "Backend", "Violation"),
    ("TASK_BLOCKS", "Task", "Task"),
    ("TASK_SPAWNS", "Task", "Task"),
    ("TASK_DECISION", "Task", "Decision"),
    ("TASK_VIOLATION", "Task", "Violation"),
    ("TASK_NOTE", "Task", "Note"),
    ("DECISION_NOTE", "Decision", "Note"),
    ("SUPERSEDES", "Decision", "Decision"),
    ("VIOLATION_RECURS", "Violation", "Violation"),
    ("SYMBOL_TASK", "CodeSymbol", "Task"),
    ("SYMBOL_VIOLATION", "CodeSymbol", "Violation"),
    ("SYMBOL_DECISION", "CodeSymbol", "Decision"),
)


def load_node_styles() -> dict[str, dict[str, Any]]:
    import json

    return cast(dict[str, dict[str, Any]], json.loads(_NODE_STYLES_PATH.read_text()))


def _rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    conn = db_get_connection()
    result = conn.execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


def _normalize_node_types(node_types: list[str] | None) -> list[str]:
    supported = {name.lower(): name for name in _NODE_LOADERS}
    if not node_types:
        return list(_NODE_LOADERS)

    normalized: list[str] = []
    for node_type in node_types:
        canonical = supported.get(node_type.lower())
        if canonical is not None and canonical not in normalized:
            normalized.append(canonical)
    return normalized or list(_NODE_LOADERS)


def _project_scope_query(
    *,
    scoped_query: str,
    global_query: str,
    project_id: str | None,
) -> list[list[Any]]:
    if project_id is not None:
        return _rows(scoped_query, {"project_id": project_id})
    return _rows(global_query)


def _load_projects(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query="""
            MATCH (p:Project {id: $project_id})
            RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at
        """,
        global_query=f"""
            MATCH (p:Project)
            RETURN p.id, p.name, p.description, p.status, p.repo_path, p.created_at
            ORDER BY p.updated_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="Project",
            metadata={
                "description": row[2],
                "status": row[3],
                "repo_path": row[4],
                "created_at": str(row[5]),
            },
        )
        for row in rows
    ]


def _load_backends(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_BACKEND]->(b:Backend)
            RETURN b.id, b.name, b.language, b.root_path, b.description, p.id
            ORDER BY b.created_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (p:Project)-[:HAS_BACKEND]->(b:Backend)
            RETURN b.id, b.name, b.language, b.root_path, b.description, p.id
            ORDER BY b.created_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="Backend",
            metadata={
                "language": row[2],
                "root_path": row[3],
                "description": row[4],
                "project_id": row[5],
            },
        )
        for row in rows
    ]


def _load_tasks(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_TASK]->(t:Task)
            RETURN t.id, t.title, t.description, t.status, t.priority, t.phase, p.id
            ORDER BY t.updated_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (p:Project)-[:HAS_TASK]->(t:Task)
            RETURN t.id, t.title, t.description, t.status, t.priority, t.phase, p.id
            ORDER BY t.updated_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="Task",
            metadata={
                "description": row[2],
                "status": row[3],
                "priority": row[4],
                "phase": row[5],
                "project_id": row[6],
            },
        )
        for row in rows
    ]


def _load_decisions(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_DECISION]->(d:Decision)
            RETURN d.id, d.title, d.rationale, d.status, d.impact, p.id
            ORDER BY d.created_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (p:Project)-[:HAS_DECISION]->(d:Decision)
            RETURN d.id, d.title, d.rationale, d.status, d.impact, p.id
            ORDER BY d.created_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="Decision",
            metadata={
                "rationale": row[2],
                "status": row[3],
                "impact": row[4],
                "project_id": row[5],
            },
        )
        for row in rows
    ]


def _load_violations(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_VIOLATION]->(v:Violation)
            RETURN v.id, v.rule, v.description, v.status, v.severity, v.file_path, p.id
            ORDER BY v.detected_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (p:Project)-[:HAS_VIOLATION]->(v:Violation)
            RETURN v.id, v.rule, v.description, v.status, v.severity, v.file_path, p.id
            ORDER BY v.detected_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="Violation",
            metadata={
                "description": row[2],
                "status": row[3],
                "severity": row[4],
                "file_path": row[5],
                "project_id": row[6],
            },
        )
        for row in rows
    ]


def _load_memories(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:PROJECT_MEMORY]->(m:Memory)
            RETURN m.id, m.content, m.kind, m.scope, m.confidence, p.id
            ORDER BY m.updated_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (m:Memory)
            OPTIONAL MATCH (p:Project)-[:PROJECT_MEMORY]->(m)
            RETURN m.id, m.content, m.kind, m.scope, m.confidence, p.id
            ORDER BY m.updated_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=(row[1] or row[0])[:72],
            type="Memory",
            metadata={
                "content": row[1],
                "kind": row[2],
                "scope": row[3],
                "confidence": row[4],
                "project_id": row[5],
            },
        )
        for row in rows
    ]


def _load_notes(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_NOTE]->(n:Note)
            RETURN n.id, n.title, n.body, n.kind, p.id
            ORDER BY n.created_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (n:Note)
            OPTIONAL MATCH (p:Project)-[:HAS_NOTE]->(n)
            RETURN n.id, n.title, n.body, n.kind, p.id
            ORDER BY n.created_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or (row[2] or row[0])[:72],
            type="Note",
            metadata={
                "body": row[2],
                "kind": row[3],
                "project_id": row[4],
            },
        )
        for row in rows
    ]


def _load_symbols(project_id: str | None, limit: int) -> list[NodeSnapshot]:
    rows = _project_scope_query(
        scoped_query=f"""
            MATCH (p:Project {{id: $project_id}})-[:HAS_BACKEND]->(:Backend)-[:BACKEND_SYMBOL]->(s:CodeSymbol)
            RETURN s.id, s.name, s.kind, s.file_path, s.language, s.signature, p.id
            ORDER BY s.indexed_at DESC
            LIMIT {limit}
        """,
        global_query=f"""
            MATCH (:Backend)-[:BACKEND_SYMBOL]->(s:CodeSymbol)
            OPTIONAL MATCH (p:Project)-[:HAS_BACKEND]->(:Backend)-[:BACKEND_SYMBOL]->(s)
            RETURN s.id, s.name, s.kind, s.file_path, s.language, s.signature, p.id
            ORDER BY s.indexed_at DESC
            LIMIT {limit}
        """,
        project_id=project_id,
    )
    return [
        NodeSnapshot(
            id=row[0],
            label=row[1] or row[0],
            type="CodeSymbol",
            metadata={
                "kind": row[2],
                "file_path": row[3],
                "language": row[4],
                "signature": row[5],
                "project_id": row[6],
            },
        )
        for row in rows
    ]


_NODE_LOADERS: dict[str, NodeLoader] = {
    "Project": _load_projects,
    "Backend": _load_backends,
    "Task": _load_tasks,
    "Decision": _load_decisions,
    "Violation": _load_violations,
    "Memory": _load_memories,
    "Note": _load_notes,
    "CodeSymbol": _load_symbols,
}


def _load_node_by_id(node_id: str) -> NodeSnapshot | None:
    for loader in _NODE_LOADERS.values():
        node = next((item for item in loader(None, 200) if item.id == node_id), None)
        if node is not None:
            return node
    return None


def _load_candidate_nodes(
    project_id: str | None,
    node_types: list[str] | None,
    max_nodes: int,
) -> dict[str, NodeSnapshot]:
    selected_types = _normalize_node_types(node_types)
    per_type_limit = max(20, (max_nodes // max(len(selected_types), 1)) + 4)
    nodes: dict[str, NodeSnapshot] = {}
    for node_type in selected_types:
        for node in _NODE_LOADERS[node_type](project_id, per_type_limit):
            nodes[node.id] = node
    return nodes


def _load_edges(candidate_ids: set[str]) -> list[EdgeSnapshot]:
    edges: list[EdgeSnapshot] = []
    seen: set[tuple[str, str, str]] = set()

    for rel_type, source_label, target_label in _EDGE_DEFINITIONS:
        rows = _rows(
            f"""
                MATCH (source:{source_label})-[:{rel_type}]->(target:{target_label})
                RETURN source.id, target.id
            """
        )
        for row in rows:
            source_id = str(row[0])
            target_id = str(row[1])
            if source_id not in candidate_ids or target_id not in candidate_ids:
                continue
            edge_key = (source_id, target_id, rel_type)
            if edge_key in seen:
                continue
            seen.add(edge_key)
            edges.append(
                EdgeSnapshot(
                    source=source_id,
                    target=target_id,
                    type=rel_type,
                    label=rel_type.replace("_", " ").title(),
                )
            )
    return edges


def _seed_ids(project_id: str | None, nodes: dict[str, NodeSnapshot]) -> set[str]:
    if project_id and project_id in nodes:
        return {project_id}

    project_ids = {node.id for node in nodes.values() if node.type == "Project"}
    return project_ids or set(nodes)


def _reachable_ids(seed_ids: set[str], edges: list[EdgeSnapshot], depth: int) -> set[str]:
    if not seed_ids:
        return set()

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    visited = set(seed_ids)
    frontier = set(seed_ids)
    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            next_frontier.update(adjacency.get(node_id, set()))
        next_frontier -= visited
        if not next_frontier:
            break
        visited.update(next_frontier)
        frontier = next_frontier
    return visited


def _trim_snapshot(
    *,
    nodes: dict[str, NodeSnapshot],
    edges: list[EdgeSnapshot],
    max_nodes: int,
) -> tuple[list[NodeSnapshot], list[EdgeSnapshot]]:
    ordered_nodes = sorted(nodes.values(), key=lambda item: (item.type, item.label.lower(), item.id))
    if len(ordered_nodes) > max_nodes:
        ordered_nodes = ordered_nodes[:max_nodes]
    allowed_ids = {node.id for node in ordered_nodes}
    ordered_edges = [
        edge
        for edge in sorted(edges, key=lambda item: (item.type, item.source, item.target))
        if edge.source in allowed_ids and edge.target in allowed_ids
    ]
    return ordered_nodes, ordered_edges


def _node_text(node: NodeSnapshot) -> str:
    values = [node.label, node.type]
    values.extend(str(value) for value in node.metadata.values() if value is not None)
    return " ".join(values).lower()


def _collect_node_relationships(
    *,
    node_id: str,
    node_type: str,
) -> list[NodeRelationship]:
    relationships: list[NodeRelationship] = []
    seen: set[tuple[str, str, str]] = set()

    for rel_type, source_label, target_label in _EDGE_DEFINITIONS:
        if node_type == source_label:
            relationships.extend(
                _collect_directional_relationships(
                    node_id=node_id,
                    rel_type=rel_type,
                    source_label=source_label,
                    target_label=target_label,
                    direction="outgoing",
                    seen=seen,
                )
            )
        if node_type == target_label:
            relationships.extend(
                _collect_directional_relationships(
                    node_id=node_id,
                    rel_type=rel_type,
                    source_label=source_label,
                    target_label=target_label,
                    direction="incoming",
                    seen=seen,
                )
            )

    relationships.sort(key=lambda item: (item.relationship, item.direction, item.node.label.lower()))
    return relationships


def _collect_directional_relationships(
    *,
    node_id: str,
    rel_type: str,
    source_label: str,
    target_label: str,
    direction: str,
    seen: set[tuple[str, str, str]],
) -> list[NodeRelationship]:
    if direction == "outgoing":
        rows = _rows(
            f"""
                MATCH (source:{source_label} {{id: $node_id}})-[:{rel_type}]->(target:{target_label})
                RETURN target.id
            """,
            {"node_id": node_id},
        )
    else:
        rows = _rows(
            f"""
                MATCH (source:{source_label})-[:{rel_type}]->(target:{target_label} {{id: $node_id}})
                RETURN source.id
            """,
            {"node_id": node_id},
        )

    relationships: list[NodeRelationship] = []
    for row in rows:
        related = _load_node_by_id(str(row[0]))
        if related is None:
            continue
        relation_key = (direction, rel_type, related.id)
        if relation_key in seen:
            continue
        seen.add(relation_key)
        relationships.append(
            NodeRelationship(
                direction=direction,
                relationship=rel_type,
                node=related,
            )
        )
    return relationships


@mcp.tool(tags={"namespace:graph"})
async def get_graph_snapshot(
    project_id: Annotated[
        str | None,
        Field(description="Optional project ID to scope the graph to."),
    ] = None,
    node_types: Annotated[
        list[str] | None,
        Field(description="Optional list of node types to include."),
    ] = None,
    depth: Annotated[
        int,
        Field(description="Maximum graph depth from the project roots.", ge=1, le=3),
    ] = 2,
    max_nodes: Annotated[
        int,
        Field(description="Maximum nodes to return in a single snapshot.", ge=20, le=400),
    ] = 240,
) -> GraphSnapshot:
    """Return a bounded graph snapshot for the dashboard canvas."""
    candidate_nodes = _load_candidate_nodes(project_id, node_types, max_nodes)
    candidate_ids = set(candidate_nodes)
    candidate_edges = _load_edges(candidate_ids)

    reachable = _reachable_ids(_seed_ids(project_id, candidate_nodes), candidate_edges, depth)
    filtered_nodes = {node_id: node for node_id, node in candidate_nodes.items() if node_id in reachable}
    filtered_edges = [
        edge
        for edge in candidate_edges
        if edge.source in filtered_nodes and edge.target in filtered_nodes
    ]
    nodes, edges = _trim_snapshot(nodes=filtered_nodes, edges=filtered_edges, max_nodes=max_nodes)

    return GraphSnapshot(
        nodes=nodes,
        edges=edges,
        available_types=list(_NODE_LOADERS),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@mcp.tool(tags={"namespace:graph"})
async def get_node_details(
    node_id: Annotated[str, Field(description="Identifier of the graph node to inspect.")],
) -> NodeDetails | dict[str, str]:
    """Return node metadata and neighboring relationships for the details panel."""
    node = _load_node_by_id(node_id)
    if node is None:
        return {"error": f"Node {node_id!r} not found."}
    return NodeDetails(node=node, relationships=_collect_node_relationships(node_id=node_id, node_type=node.type))


@mcp.tool(tags={"namespace:graph"})
async def search_graph(
    query: Annotated[str, Field(description="Plain-text query to match against graph nodes.")],
    project_id: Annotated[
        str | None,
        Field(description="Optional project ID to scope the search to."),
    ] = None,
    node_types: Annotated[
        list[str] | None,
        Field(description="Optional list of node types to search."),
    ] = None,
    limit: Annotated[int, Field(description="Maximum search results to return.", ge=1, le=50)] = 20,
) -> list[NodeSnapshot]:
    """Perform a bounded text search across visible graph node metadata."""
    cleaned_query = query.strip().lower()
    if not cleaned_query:
        return []

    candidate_nodes = _load_candidate_nodes(project_id, node_types, max(limit * 4, 80))
    tokens = [token for token in cleaned_query.split() if token]
    ranked: list[tuple[int, NodeSnapshot]] = []

    for node in candidate_nodes.values():
        haystack = _node_text(node)
        if cleaned_query not in haystack and not all(token in haystack for token in tokens):
            continue

        score = 0
        if cleaned_query in node.label.lower():
            score += 10
        score += sum(2 for token in tokens if token in haystack)
        ranked.append((score, node))

    ranked.sort(key=lambda item: (-item[0], item[1].type, item[1].label.lower()))
    return [node for _, node in ranked[:limit]]