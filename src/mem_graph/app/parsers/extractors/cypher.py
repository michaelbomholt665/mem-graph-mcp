"""
cypher.py — Cypher query extractor (fallback to AST traversal).

Note: The cypher binary in the repo is a mis-packaged Haskell parser.
This extractor will silently return an empty result if the grammar fails
to load, and is ready for use once a real Cypher parser binary is sourced.
"""

from __future__ import annotations

import logging
from typing import Any

from ..safety import SafetyContext
from ..types import ExtractedEdge, ExtractedNode, NodeKind, ParsedFile
from .base import (
    BaseExtractor,
    make_contains_edge,
    make_file_edge,
    make_file_id,
    make_file_symbol,
    make_symbol_id,
    node_line_end,
    node_line_start,
    node_text,
)

logger = logging.getLogger(__name__)

# Node types recognised as Cypher constructs when the grammar is available
_QUERY_TYPES = frozenset({"query", "statement", "single_query", "multi_part_query"})
_CLAUSE_TYPES = frozenset(
    {
        "match_clause",
        "create_clause",
        "merge_clause",
        "return_clause",
        "where_clause",
        "with_clause",
        "unwind_clause",
        "delete_clause",
        "set_clause",
        "remove_clause",
        "call_clause",
    }
)
_LABEL_TYPES = frozenset({"label", "node_label", "rel_type_name"})


class CypherExtractor(BaseExtractor):
    """AST-walk extractor for Cypher queries."""

    @property
    def language_key(self) -> str:
        return "cypher"

    def extract(
        self,
        parsed: ParsedFile,
        ctx: SafetyContext,
    ) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
        nodes: list[ExtractedNode] = []
        edges: list[ExtractedEdge] = []

        tree = parsed._tree
        source = parsed.content
        file_path = parsed.path

        if tree is None:
            return nodes, edges

        root = tree.root_node
        # If the root type suggests a Haskell grammar, bail out gracefully
        if root.type not in ("program", "source_file", "query", "statements", "ERROR"):
            logger.debug(
                "Cypher grammar may be wrong (root_type=%s); skipping extraction",
                root.type,
            )
            return nodes, edges

        line_count = root.end_point[0] + 1
        file_id = make_file_id(file_path)
        file_sym = make_file_symbol(file_path, "cypher", line_count, NodeKind.QUERY)
        nodes.append(file_sym)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))
        ctx.inc_symbols()

        self._walk(
            root, source, file_path, file_id, file_sym.symbol_id, nodes, edges, ctx
        )
        return nodes, edges

    def _walk(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        if not ctx.check_deadline():
            return

        for child in node.children:
            if not ctx.inc_nodes():
                return
            t = child.type

            if t in _CLAUSE_TYPES:
                self._process_clause(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif t in _LABEL_TYPES:
                self._process_label(child, source, file_path, parent_id, nodes, ctx)
            else:
                self._walk(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )

    def _process_clause(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        ls = node_line_start(node)
        le = node_line_end(node)
        qname = f"{node.type}@{ls}"
        sid = make_symbol_id(
            "cypher", file_path, NodeKind.QUERY.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=node.type,
            qualified_name=qname,
            kind=NodeKind.QUERY,
            file_path=file_path,
            language="cypher",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            capture_reason=node.type,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges()
        self._walk(node, source, file_path, file_id, sid, nodes, edges, ctx)

    def _process_label(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        ctx: SafetyContext,
    ) -> None:
        name = node_text(node, source)
        if not name:
            return
        ls = node_line_start(node)
        le = node_line_end(node)
        qname = f"label::{name}@{ls}"
        sid = make_symbol_id(
            "cypher", file_path, NodeKind.LABEL.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.LABEL,
            file_path=file_path,
            language="cypher",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        ctx.inc_edges()
