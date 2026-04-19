"""
python.py — Custom Python extractor.

Produces symbols for: module, class, function, method, import, call,
type alias, constants, and anonymous symbols (lambda, nested function
when returned/passed/decorated).
"""

from __future__ import annotations

import logging
from typing import Any

from ..safety import SafetyContext
from ..types import (
    EdgeKind,
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


class PythonExtractor(BaseExtractor):
    """Custom Python extractor using tree-sitter AST traversal."""

    @property
    def language_key(self) -> str:
        return "python"

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

        file_sym = make_file_symbol(file_path, "python", line_count, NodeKind.MODULE)
        nodes.append(file_sym)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))
        ctx.inc_symbols()

        self._visit(
            root, source, file_path, file_id, file_sym.symbol_id, "", nodes, edges, ctx
        )
        return nodes, edges

    # ------------------------------------------------------------------
    # Tree traversal
    # ------------------------------------------------------------------

    def _visit(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        if not ctx.check_deadline():
            return

        for child in node.children:
            if not ctx.inc_nodes():
                return
            ntype = child.type

            if ntype in ("class_definition", "decorated_definition"):
                self._handle_class(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )
            elif ntype in ("function_definition", "async_function_definition"):
                self._handle_function(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )
            elif ntype == "import_statement":
                self._handle_import(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif ntype == "import_from_statement":
                self._handle_import_from(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif ntype == "expression_statement":
                self._handle_expression(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )
            elif ntype == "call":
                self._handle_call(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            else:
                self._visit(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )

    def _handle_class(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        # Unwrap decorator if needed
        actual = node
        decorators = []
        if node.type == "decorated_definition":
            for ch in node.children:
                if ch.type == "decorator":
                    decorators.append(ch)
                else:
                    actual = ch

        if actual.type not in ("class_definition",):
            if actual.type in ("function_definition", "async_function_definition"):
                self._handle_function(
                    node,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )
            return

        name_node = actual.child_by_field_name("name")
        if name_node is None:
            return
        name = node_text(name_node, source)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(actual)
        le = node_line_end(actual)
        sid = make_symbol_id("python", file_path, NodeKind.CLASS.value, qname, ls, le)

        sig_parts = [f"class {name}"]
        bases = actual.child_by_field_name("superclasses")
        if bases:
            sig_parts.append(f"({node_text(bases, source)})")

        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.CLASS,
            file_path=file_path,
            language="python",
            line_start=ls,
            line_end=le,
            signature="".join(sig_parts),
            parent_id=parent_id,
            is_exported=not name.startswith("_"),
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)

        body = actual.child_by_field_name("body")
        if body:
            self._visit(body, source, file_path, file_id, sid, qname, nodes, edges, ctx)

    def _handle_function(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        actual = node
        if node.type == "decorated_definition":
            for ch in node.children:
                if ch.type not in ("decorator",):
                    actual = ch
                    break

        is_async = actual.type == "async_function_definition"
        name_node = actual.child_by_field_name("name")
        if name_node is None:
            return
        name = node_text(name_node, source)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(actual)
        le = node_line_end(actual)

        # method or function?
        kind = NodeKind.FUNCTION
        if scope_prefix and "." in scope_prefix:
            kind = NodeKind.METHOD

        sid = make_symbol_id("python", file_path, kind.value, qname, ls, le)

        params_node = actual.child_by_field_name("parameters")
        sig = f"{'async ' if is_async else ''}def {name}{node_text(params_node, source) if params_node else '()'}"

        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            language="python",
            line_start=ls,
            line_end=le,
            signature=sig,
            parent_id=parent_id,
            is_async=is_async,
            is_exported=not name.startswith("_"),
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)

        body = actual.child_by_field_name("body")
        if body:
            self._visit(body, source, file_path, file_id, sid, qname, nodes, edges, ctx)

    def _handle_import(
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
        for child in node.children:
            if child.type in ("dotted_name", "aliased_import"):
                name = node_text(child, source).split(" as ")[0].strip()
                ls = node_line_start(node)
                le = node_line_end(node)
                qname = f"import::{name}"
                sid = make_symbol_id(
                    "python", file_path, NodeKind.IMPORT.value, qname, ls, le
                )
                sym = ExtractedNode(
                    symbol_id=sid,
                    name=name,
                    qualified_name=qname,
                    kind=NodeKind.IMPORT,
                    file_path=file_path,
                    language="python",
                    line_start=ls,
                    line_end=le,
                    parent_id=parent_id,
                )
                if not ctx.inc_symbols():
                    return
                nodes.append(sym)
                edges.append(make_contains_edge(parent_id, sid))
                ctx.inc_edges()

    def _handle_import_from(
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
        module_node = (
            node.child_by_field_name("module_name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        module = node_text(module_node, source) if module_node else ""
        ls = node_line_start(node)
        le = node_line_end(node)
        text = node_text(node, source)
        qname = f"import_from::{module}::{text[:60]}"
        sid = make_symbol_id("python", file_path, NodeKind.IMPORT.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=module or text[:40],
            qualified_name=qname,
            kind=NodeKind.IMPORT,
            file_path=file_path,
            language="python",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges()

    def _handle_expression(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        for child in node.children:
            if child.type == "assignment":
                self._handle_assignment(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    nodes,
                    edges,
                    ctx,
                )
            elif child.type == "call":
                self._handle_call(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )

    def _handle_assignment(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        left = (
            node.child_by_field_name("left")
            if hasattr(node, "child_by_field_name")
            else None
        )
        right = (
            node.child_by_field_name("right")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if left is None:
            return
        name = node_text(left, source)
        # Only top-level or class-level constants / type aliases
        if not name.isupper() and not (right and right.type in ("lambda",)):
            return
        ls = node_line_start(node)
        le = node_line_end(node)
        kind = NodeKind.CONSTANT if name.isupper() else NodeKind.VARIABLE
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        sid = make_symbol_id("python", file_path, kind.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            language="python",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=not name.startswith("_"),
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges()

    def _handle_call(
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
        fn_node = (
            node.child_by_field_name("function")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if fn_node is None:
            return
        call_name = node_text(fn_node, source)
        if not call_name or len(call_name) > 120:
            return
        ls = node_line_start(node)
        le = node_line_end(node)
        qname = f"call::{call_name}@{ls}"
        sid = make_symbol_id("python", file_path, NodeKind.CALL.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=call_name,
            qualified_name=qname,
            kind=NodeKind.CALL,
            file_path=file_path,
            language="python",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(ExtractedEdge(kind=EdgeKind.CALLS, from_id=parent_id, to_id=sid))
        ctx.inc_edges()
