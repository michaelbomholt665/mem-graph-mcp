"""
tsx.py — TSX extractor (TypeScript + JSX-specific behavior).

Reuses TypeScriptExtractor and adds JSX custom element detection.
"""

from __future__ import annotations

import logging
from typing import Any

from ..safety import SafetyContext
from ..types import ExtractedEdge, ExtractedNode, NodeKind, ParsedFile
from .base import (
    make_contains_edge,
    make_file_id,
    make_symbol_id,
    node_line_end,
    node_line_start,
    node_text,
)
from .typescript import TypeScriptExtractor

logger = logging.getLogger(__name__)


class TsxExtractor(TypeScriptExtractor):
    """TSX extractor — TypeScript extraction with JSX component detection."""

    def __init__(self) -> None:
        super().__init__(lang_key="tsx")

    @property
    def language_key(self) -> str:
        return "tsx"

    def extract(
        self,
        parsed: ParsedFile,
        ctx: SafetyContext,
    ) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
        nodes, edges = super().extract(parsed, ctx)
        if parsed._tree is not None:
            self._extract_jsx(
                parsed._tree.root_node, parsed.content, parsed.path, nodes, edges, ctx
            )
        return nodes, edges

    def _extract_jsx(
        self,
        root: Any,
        source: bytes,
        file_path: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        file_id = make_file_id(file_path)
        self._walk_jsx(root, source, file_path, file_id, None, nodes, edges, ctx)

    def _walk_jsx(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str | None,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        if not ctx.check_deadline():
            return

        if node.type in ("jsx_element", "jsx_self_closing_element"):
            self._process_jsx_element(
                node, source, file_path, file_id, parent_id, nodes, edges, ctx
            )

        for child in node.children:
            ctx.inc_nodes()
            self._walk_jsx(
                child, source, file_path, file_id, parent_id, nodes, edges, ctx
            )

    def _process_jsx_element(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str | None,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        name_node = self._get_jsx_name_node(node)
        if not name_node:
            return

        name = node_text(name_node, source)
        # Only custom components (capitalized)
        if not name or not name[0].isupper():
            return

        ls = node_line_start(node)
        le = node_line_end(node)
        qname = f"jsx::{name}@{ls}"
        sid = make_symbol_id("tsx", file_path, NodeKind.CALL.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.CALL,
            file_path=file_path,
            language="tsx",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            capture_reason="jsx_component",
        )
        if ctx.inc_symbols():
            nodes.append(sym)
            if parent_id:
                edges.append(make_contains_edge(parent_id, sid))
                ctx.inc_edges()
    def _get_jsx_name_node(self, node: Any) -> Any | None:
        """Resolve the name node for a JSX element."""
        tag_node = (
            node.child_by_field_name("open_tag")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if tag_node is None and node.type == "jsx_self_closing_element":
            tag_node = node
        if not tag_node:
            return None

        name_node = (
            tag_node.child_by_field_name("name")
            if hasattr(tag_node, "child_by_field_name")
            else None
        )
        if name_node is None:
            for ch in tag_node.children:
                if ch.type in (
                    "identifier",
                    "member_expression",
                    "jsx_namespace_name",
                ):
                    return ch
        return name_node
