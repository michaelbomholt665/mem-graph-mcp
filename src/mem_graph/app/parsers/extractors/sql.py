"""
sql.py — SQL extractor.

Uses the tree-sitter-sql grammar node names discovered in Task 023:
select, from, join, cte, relation, field, invocation.
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

# SQL grammar node types → semantic meanings
_STATEMENT_TYPES = frozenset(
    {
        "select",
        "select_statement",
        "insert",
        "insert_statement",
        "update",
        "update_statement",
        "delete",
        "delete_statement",
        "create_table",
        "create_table_statement",
        "create_index",
        "create_index_statement",
        "alter_table",
        "alter_table_statement",
        "drop_table",
        "drop_statement",
    }
)
_CTE_TYPES = frozenset({"cte", "common_table_expression", "with_clause"})
_TABLE_TYPES = frozenset({"relation", "table_reference", "from_item", "table_name"})
_CALL_TYPES = frozenset({"invocation", "function_call", "function_application"})


class SqlExtractor(BaseExtractor):
    """AST-walk extractor for SQL files."""

    @property
    def language_key(self) -> str:
        return "sql"

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
        line_count = root.end_point[0] + 1
        file_id = make_file_id(file_path)

        file_sym = make_file_symbol(file_path, "sql", line_count, NodeKind.QUERY)
        nodes.append(file_sym)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))
        ctx.inc_symbols()

        self._walk(
            root, source, file_path, file_id, file_sym.symbol_id, 0, nodes, edges, ctx
        )
        return nodes, edges

    def _walk(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        depth: int,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        if not ctx.check_deadline() or depth > 8:
            return

        for child in node.children:
            if not ctx.inc_nodes():
                return
            t = child.type

            if t in _STATEMENT_TYPES:
                self._handle_statement(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    depth,
                    nodes,
                    edges,
                    ctx,
                )
            elif t in _CTE_TYPES:
                self._handle_cte(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    depth,
                    nodes,
                    edges,
                    ctx,
                )
            elif t in _TABLE_TYPES:
                self._handle_table(child, source, file_path, parent_id, nodes, ctx)
            elif t in _CALL_TYPES:
                self._handle_call(child, source, file_path, parent_id, nodes, ctx)
            else:
                self._walk(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    depth + 1,
                    nodes,
                    edges,
                    ctx,
                )

    def _handle_statement(
        self,
        child: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        depth: int,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        ls = node_line_start(child)
        le = node_line_end(child)
        qname = f"stmt::{child.type}@{ls}"
        sid = make_symbol_id("sql", file_path, NodeKind.QUERY.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=child.type,
            qualified_name=qname,
            kind=NodeKind.QUERY,
            file_path=file_path,
            language="sql",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)
        self._walk(child, source, file_path, file_id, sid, depth + 1, nodes, edges, ctx)

    def _handle_cte(
        self,
        child: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        depth: int,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        name_node = (
            child.child_by_field_name("name")
            if hasattr(child, "child_by_field_name")
            else None
        )
        name = (
            node_text(name_node, source)
            if name_node
            else f"cte@{node_line_start(child)}"
        )
        if not name:
            name = f"cte@{node_line_start(child)}"
        ls = node_line_start(child)
        le = node_line_end(child)
        qname = f"cte::{name}"
        sid = make_symbol_id("sql", file_path, NodeKind.CTE.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.CTE,
            file_path=file_path,
            language="sql",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges()
        self._walk(child, source, file_path, file_id, sid, depth + 1, nodes, edges, ctx)

    def _handle_table(
        self,
        child: Any,
        source: bytes,
        file_path: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        ctx: SafetyContext,
    ) -> None:
        name = node_text(child, source).split()[0][:80]
        if not name:
            return
        ls = node_line_start(child)
        le = node_line_end(child)
        qname = f"table::{name}@{ls}"
        sid = make_symbol_id("sql", file_path, NodeKind.TABLE.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.TABLE,
            file_path=file_path,
            language="sql",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        ctx.inc_edges()

    def _handle_call(
        self,
        child: Any,
        source: bytes,
        file_path: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        ctx: SafetyContext,
    ) -> None:
        name_node = (
            child.child_by_field_name("name")
            if hasattr(child, "child_by_field_name")
            else None
        )
        name = (
            node_text(name_node, source)
            if name_node
            else node_text(child, source).split("(")[0][:40]
        )
        if not name:
            return
        ls = node_line_start(child)
        le = node_line_end(child)
        qname = f"call::{name}@{ls}"
        sid = make_symbol_id("sql", file_path, NodeKind.CALL.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.CALL,
            file_path=file_path,
            language="sql",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        ctx.inc_edges()
