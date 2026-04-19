"""
persist.py — Pure DTO → Cypher statement/batch construction.

Must not own:
- DB connections
- Query execution
- Retry logic
- Transaction state
- Ladybug imports

Input:  parser/resolver DTOs (ExtractedNode, ExtractedEdge, etc.)
Output: CypherBatch objects ready for ingest.py to execute.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .types import EdgeKind, ExtractedEdge, ExtractedNode

# ---------------------------------------------------------------------------
# Batch DTOs
# ---------------------------------------------------------------------------


@dataclass
class NodeBatch:
    """A batch of CodeSymbol upsert operations."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, rec: dict[str, Any]) -> None:
        self.records.append(rec)


@dataclass
class EdgeBatch:
    """A batch of relationship upsert operations."""

    kind: str
    records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, rec: dict[str, Any]) -> None:
        self.records.append(rec)


@dataclass
class FileBatch:
    """A single CodeFile upsert."""

    record: dict[str, Any] = field(default_factory=dict)


@dataclass
class CypherBatch:
    """Complete set of batches for one file ingestion."""

    file_batch: FileBatch = field(default_factory=FileBatch)
    symbol_batch: NodeBatch = field(default_factory=NodeBatch)
    edge_batches: dict[str, EdgeBatch] = field(default_factory=dict)
    stale_cleanup_ids: list[str] = field(default_factory=list)
    embedding_updates: list[dict[str, Any]] = field(default_factory=list)

    def edge_batch(self, kind: str) -> EdgeBatch:
        if kind not in self.edge_batches:
            self.edge_batches[kind] = EdgeBatch(kind=kind)
        return self.edge_batches[kind]


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------


def symbol_id(
    language: str,
    file_path: str,
    kind: str,
    qualified_name: str,
    line_start: int,
    line_end: int,
) -> str:
    key = f"{language}:{file_path}:{kind}:{qualified_name}:{line_start}:{line_end}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def file_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Statement strings (executed by ingest.py)
# ---------------------------------------------------------------------------

# Note: Ladybug does NOT support MERGE — use explicit MATCH + CREATE.
# We use UNWIND for batch node/rel creation.

UPSERT_CODE_FILE = """
UNWIND $records AS r
OPTIONAL MATCH (f:CodeFile {id: r.id})
CALL {{
    WITH f, r
    WHERE f IS NULL
    CREATE (:CodeFile {
        id: r.id,
        path: r.path,
        name: r.name,
        language: r.language,
        size_bytes: r.size_bytes,
        content_hash: r.content_hash,
        summary: r.summary,
        indexed_at: current_timestamp(),
        updated_at: current_timestamp()
    })
    UNION
    WITH f, r
    WHERE f IS NOT NULL
    SET f.path = r.path,
        f.name = r.name,
        f.language = r.language,
        f.size_bytes = r.size_bytes,
        f.content_hash = r.content_hash,
        f.summary = r.summary,
        f.updated_at = current_timestamp()
}}
"""

UPSERT_CODE_SYMBOL = """
UNWIND $records AS r
OPTIONAL MATCH (s:CodeSymbol {id: r.id})
CALL {{
    WITH s, r
    WHERE s IS NULL
    CREATE (:CodeSymbol {
        id: r.id,
        name: r.name,
        kind: r.kind,
        file_path: r.file_path,
        language: r.language,
        signature: r.signature,
        qualified_name: r.qualified_name,
        parent_id: r.parent_id,
        line_start: r.line_start,
        line_end: r.line_end,
        is_exported: r.is_exported,
        is_async: r.is_async,
        indexed_at: current_timestamp()
    })
    UNION
    WITH s, r
    WHERE s IS NOT NULL
    SET s.name = r.name,
        s.kind = r.kind,
        s.file_path = r.file_path,
        s.language = r.language,
        s.signature = r.signature,
        s.qualified_name = r.qualified_name,
        s.parent_id = r.parent_id,
        s.line_start = r.line_start,
        s.line_end = r.line_end,
        s.is_exported = r.is_exported,
        s.is_async = r.is_async
}}
"""

_REL_UPSERT_TEMPLATES: dict[str, str] = {
    EdgeKind.FILE_SYMBOL.value: """
UNWIND $records AS r
MATCH (f:CodeFile {id: r.from_id}), (s:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (f)-[e:FILE_SYMBOL]->(s)
CALL {{
    WITH f, s, e
    WHERE e IS NULL
    CREATE (f)-[:FILE_SYMBOL]->(s)
}}
""",
    EdgeKind.CONTAINS.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:CONTAINS]->(b)
CALL {{
    WITH a, b, e
    WHERE e IS NULL
    CREATE (a)-[:CONTAINS]->(b)
}}
""",
    EdgeKind.IMPORTS.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:IMPORTS]->(b)
CALL {{
    WITH a, b, e, r
    WHERE e IS NULL
    CREATE (a)-[:IMPORTS {module_path: r.module_path, alias: r.alias, is_relative: r.is_relative}]->(b)
}}
""",
    EdgeKind.CALLS.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:CALLS]->(b)
CALL {{
    WITH a, b, e, r
    WHERE e IS NULL
    CREATE (a)-[:CALLS {call_name: r.call_name, is_awaited: r.is_awaited}]->(b)
}}
""",
    EdgeKind.RESOLVES_TO.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:RESOLVES_TO]->(b)
CALL {{
    WITH a, b, e, r
    WHERE e IS NULL
    CREATE (a)-[:RESOLVES_TO {confidence: r.confidence, resolver: r.resolver}]->(b)
}}
""",
    EdgeKind.EXTENDS.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:EXTENDS]->(b)
CALL {{
    WITH a, b, e
    WHERE e IS NULL
    CREATE (a)-[:EXTENDS]->(b)
}}
""",
    EdgeKind.IMPLEMENTS_SYMBOL.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:IMPLEMENTS_SYMBOL]->(b)
CALL {{
    WITH a, b, e
    WHERE e IS NULL
    CREATE (a)-[:IMPLEMENTS_SYMBOL]->(b)
}}
""",
    EdgeKind.READS_FROM.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:READS_FROM]->(b)
CALL {{
    WITH a, b, e
    WHERE e IS NULL
    CREATE (a)-[:READS_FROM]->(b)
}}
""",
    EdgeKind.ALIASES.value: """
UNWIND $records AS r
MATCH (a:CodeSymbol {id: r.from_id}), (b:CodeSymbol {id: r.to_id})
OPTIONAL MATCH (a)-[e:ALIASES]->(b)
CALL {{
    WITH a, b, e
    WHERE e IS NULL
    CREATE (a)-[:ALIASES]->(b)
}}
""",
}


def get_rel_template(kind: str) -> str | None:
    return _REL_UPSERT_TEMPLATES.get(kind)


STALE_SYMBOL_CLEANUP = """
UNWIND $stale_ids AS sid
MATCH (s:CodeSymbol {id: sid})
WHERE NOT EXISTS {{
    (s)-[:SYMBOL_TASK]->(:Task)
    | (s)-[:SYMBOL_DECISION]->(:Decision)
    | (s)-[:SYMBOL_VIOLATION]->(:Violation)
}}
DETACH DELETE s
"""

# ---------------------------------------------------------------------------
# Batch builder
# ---------------------------------------------------------------------------


def build_batch(
    file_path: str,
    language_key: str,
    nodes: list[ExtractedNode],
    edges: list[ExtractedEdge],
    file_size: int = 0,
    content_hash: str = "",
    max_batch: int = 500,
) -> CypherBatch:
    """Convert DTO lists into a CypherBatch ready for ingest."""
    batch = CypherBatch()

    # File record
    fid = file_id(file_path)
    batch.file_batch.record = {
        "id": fid,
        "path": file_path,
        "name": file_path.rsplit("/", 1)[-1],
        "language": language_key,
        "size_bytes": file_size,
        "content_hash": content_hash,
        "summary": "",
    }

    # Symbol records (bounded)
    seen_ids: set[str] = set()
    for node in nodes[:max_batch]:
        if node.symbol_id in seen_ids:
            continue
        seen_ids.add(node.symbol_id)
        batch.symbol_batch.add(
            {
                "id": node.symbol_id,
                "name": node.name,
                "kind": node.kind.value,
                "file_path": file_path,
                "language": language_key,
                "signature": node.signature,
                "qualified_name": node.qualified_name,
                "parent_id": node.parent_id or "",
                "line_start": node.line_start,
                "line_end": node.line_end,
                "is_exported": node.is_exported,
                "is_async": node.is_async,
            }
        )

    # Edge records (bounded, grouped by kind)
    edge_count = 0
    for edge in edges:
        if edge_count >= max_batch * 4:
            break
        kind_str = edge.kind.value
        if kind_str not in _REL_UPSERT_TEMPLATES:
            continue
        rec: dict[str, Any] = {"from_id": edge.from_id, "to_id": edge.to_id}
        # Merge edge props
        rec.update(edge.props)
        # Ensure required fields exist per relationship type
        if kind_str == EdgeKind.IMPORTS.value:
            rec.setdefault("module_path", "")
            rec.setdefault("alias", "")
            rec.setdefault("is_relative", False)
        elif kind_str == EdgeKind.CALLS.value:
            rec.setdefault("call_name", "")
            rec.setdefault("is_awaited", False)
        elif kind_str == EdgeKind.RESOLVES_TO.value:
            rec.setdefault("confidence", 0.5)
            rec.setdefault("resolver", "")
        batch.edge_batch(kind_str).add(rec)
        edge_count += 1

    return batch
