"""
universal.py — Shallow extractor for simple / config grammars.

Uses the canonical .scm query when available, otherwise falls back to a
depth-limited AST walk that emits top-level named nodes as ELEMENT symbols.

Simple grammars: css, go.mod, go.sum, html, java, javascript, json, proto,
toml, yaml.
"""

from __future__ import annotations

import logging

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
from .scm import ScmExtractor

logger = logging.getLogger(__name__)

# Grammars for which we use the universal (shallow) strategy
UNIVERSAL_LANGUAGES: frozenset[str] = frozenset(
    {
        "css",
        "go.mod",
        "go.sum",
        "html",
        "java",
        "javascript",
        "json",
        "proto",
        "toml",
        "yaml",
    }
)

# Max depth for the AST walk fallback
_MAX_WALK_DEPTH = 3

# Node types that should never become symbols
_SKIP_TYPES = frozenset(
    {
        "comment",
        "block_comment",
        "line_comment",
        "string",
        "number",
        "boolean",
        "null",
        "(",
        ")",
        "{",
        "}",
        "[",
        "]",
        ";",
        ",",
        ".",
        ":",
        "=",
        "+",
        "-",
        "*",
        "/",
    }
)


class UniversalExtractor(BaseExtractor):
    """Shallow AST symbol extractor for config / simple grammars."""

    def __init__(self, lang_key: str) -> None:
        self._lang_key = lang_key
        self._scm = ScmExtractor(lang_key)

    @property
    def language_key(self) -> str:
        return self._lang_key

    def extract(
        self,
        parsed: ParsedFile,
        ctx: SafetyContext,
    ) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
        # Try SCM extractor first; fall back to AST walk if it yields nothing
        scm_nodes, scm_edges = self._scm.extract(parsed, ctx)
        if len(scm_nodes) > 1:  # >1 because file symbol is always emitted
            return scm_nodes, scm_edges

        return self._walk_extract(parsed, ctx)

    def _walk_extract(
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

        file_sym = make_file_symbol(file_path, self._lang_key, line_count)
        if not ctx.inc_symbols():
            return nodes, edges
        nodes.append(file_sym)
        file_id = make_file_id(file_path)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))

        self._walk(
            root,
            depth=0,
            source=source,
            file_path=file_path,
            parent_id=file_sym.symbol_id,
            file_id=file_id,
            nodes=nodes,
            edges=edges,
            ctx=ctx,
        )
        return nodes, edges

    def _walk(
        self,
        node: object,
        depth: int,
        source: bytes,
        file_path: str,
        parent_id: str,
        file_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        if depth > _MAX_WALK_DEPTH:
            return
        if not ctx.check_deadline():
            return

        for child in node.children:  # type: ignore[attr-defined]
            if not ctx.inc_nodes():
                return
            if child.type in _SKIP_TYPES or not child.is_named:
                continue

            name = node_text(child, source)
            if not name or len(name) > 200:
                continue

            ls = node_line_start(child)
            le = node_line_end(child)
            sid = make_symbol_id(
                language=self._lang_key,
                file_path=file_path,
                kind=NodeKind.ELEMENT.value,
                qualified_name=f"{file_path}::{name}@{ls}",
                line_start=ls,
                line_end=le,
            )
            sym = ExtractedNode(
                symbol_id=sid,
                name=name[:120],
                qualified_name=f"{file_path}::{name}@{ls}",
                kind=NodeKind.ELEMENT,
                file_path=file_path,
                language=self._lang_key,
                line_start=ls,
                line_end=le,
                parent_id=parent_id,
            )
            if not ctx.inc_symbols():
                return
            nodes.append(sym)
            edges.append(make_file_edge(file_id, sid))
            edges.append(make_contains_edge(parent_id, sid))
            if not ctx.inc_edges(2):
                return

            self._walk(
                child,
                depth + 1,
                source,
                file_path,
                sid,
                file_id,
                nodes,
                edges,
                ctx,
            )
