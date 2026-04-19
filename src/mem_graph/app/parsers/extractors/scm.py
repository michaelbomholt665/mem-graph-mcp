"""
scm.py — Query-backed extractor using the canonical {language}.scm file.

Runs the pre-compiled tree-sitter query against the AST and maps captures
to ExtractedNode + ExtractedEdge records.
"""

from __future__ import annotations

import logging
from typing import Any

from ..assets import get_manifest
from ..loader import load_query_from_manifest
from ..safety import SafetyContext
from ..types import (
    ExtractedEdge,
    ExtractedNode,
    NodeKind,
    ParsedFile,
)
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

# Capture-name prefix → NodeKind mappings (non-exhaustive; unknown → ELEMENT)
_CAPTURE_KIND_MAP: dict[str, NodeKind] = {
    "name.definition.function": NodeKind.FUNCTION,
    "name.definition.method": NodeKind.METHOD,
    "name.definition.class": NodeKind.CLASS,
    "name.definition.interface": NodeKind.INTERFACE,
    "name.definition.module": NodeKind.MODULE,
    "name.definition.type": NodeKind.TYPE,
    "name.definition.macro": NodeKind.FUNCTION,
    "name.definition.constant": NodeKind.CONSTANT,
    "name.definition.field": NodeKind.VARIABLE,
    "name.definition.enum": NodeKind.ENUM,
    "name.definition.struct": NodeKind.STRUCT,
    "name.definition.namespace": NodeKind.MODULE,
    "definition.function": NodeKind.FUNCTION,
    "definition.method": NodeKind.METHOD,
    "definition.class": NodeKind.CLASS,
    "definition.interface": NodeKind.INTERFACE,
    "definition.type": NodeKind.TYPE,
    "definition.struct": NodeKind.STRUCT,
    "definition.enum": NodeKind.ENUM,
}


def _kind_from_capture(capture_name: str) -> NodeKind:
    for prefix, kind in _CAPTURE_KIND_MAP.items():
        if capture_name == prefix or capture_name.endswith(f".{prefix}"):
            return kind
    if "function" in capture_name:
        return NodeKind.FUNCTION
    if "class" in capture_name or "type" in capture_name:
        return NodeKind.CLASS
    if "method" in capture_name:
        return NodeKind.METHOD
    if "import" in capture_name:
        return NodeKind.IMPORT
    return NodeKind.ELEMENT


class ScmExtractor(BaseExtractor):
    """Runs the canonical .scm query and maps named captures to symbols."""

    def __init__(self, lang_key: str) -> None:
        self._lang_key = lang_key

    @property
    def language_key(self) -> str:
        return self._lang_key

    def extract(
        self,
        parsed: ParsedFile,
        ctx: SafetyContext,
    ) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
        nodes: list[ExtractedNode] = []
        edges: list[ExtractedEdge] = []

        source = parsed.content
        tree = parsed._tree
        language = parsed._language
        file_path = parsed.path

        if tree is None or language is None:
            return nodes, edges

        manifest = get_manifest(self._lang_key)
        if manifest is None:
            return nodes, edges

        query = load_query_from_manifest(manifest, language)
        if query is None:
            return nodes, edges

        root = tree.root_node
        line_count = root.end_point[0] + 1

        file_sym = make_file_symbol(file_path, self._lang_key, line_count)
        if not ctx.inc_symbols():
            return nodes, edges
        nodes.append(file_sym)
        file_id = make_file_id(file_path)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))

        # Execute query and process captures
        try:
            captures: dict[str, list[Any]] = query.captures(root)
        except Exception as exc:
            logger.debug("Query capture failed for %s: %s", self._lang_key, exc)
            return nodes, edges

        self._process_captures(
            captures, source, file_path, file_id, file_sym, nodes, edges, ctx
        )
        return nodes, edges

    def _process_captures(
        self,
        captures: dict[str, list[Any]],
        source: bytes,
        file_path: str,
        file_id: str,
        file_sym: ExtractedNode,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        for capture_name, capture_nodes in captures.items():
            if not ctx.inc_captures(len(capture_nodes)):
                break
            if not ctx.check_deadline():
                break

            for node in capture_nodes:
                if not ctx.inc_symbols():
                    return

                name = node_text(node, source)
                if not name or len(name) > 200:
                    continue

                self._create_symbol(
                    name, node, capture_name, source, file_path, file_id, file_sym,
                    nodes, edges, ctx
                )

    def _create_symbol(
        self,
        name: str,
        node: Any,
        capture_name: str,
        source: bytes,
        file_path: str,
        file_id: str,
        file_sym: ExtractedNode,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        kind = _kind_from_capture(capture_name)
        ls = node_line_start(node)
        le = node_line_end(node)
        qname = f"{file_path}::{name}"
        sid = make_symbol_id(
            language=self._lang_key,
            file_path=file_path,
            kind=kind.value,
            qualified_name=qname,
            line_start=ls,
            line_end=le,
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            capture_reason=capture_name,
            parent_id=file_sym.symbol_id,
        )
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(file_sym.symbol_id, sid))
        if not ctx.inc_edges(2):
            return
