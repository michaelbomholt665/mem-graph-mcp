"""
go.py — Custom Go extractor.

Produces symbols for: package, function, method, struct, interface,
import, call, goroutine, defer, channel, and anonymous function literals
where semantically relevant.
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


class GoExtractor(BaseExtractor):
    """Custom Go extractor using tree-sitter AST traversal."""

    @property
    def language_key(self) -> str:
        return "go"

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

        file_sym = make_file_symbol(file_path, "go", line_count, NodeKind.MODULE)
        nodes.append(file_sym)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))
        ctx.inc_symbols()

        # Extract package name
        pkg_sym_id = self._handle_package(
            root, source, file_path, file_id, file_sym.symbol_id, nodes, edges, ctx
        )

        self._visit_top(
            root,
            source,
            file_path,
            file_id,
            pkg_sym_id or file_sym.symbol_id,
            nodes,
            edges,
            ctx,
        )
        return nodes, edges

    # ------------------------------------------------------------------

    def _handle_package(
        self,
        root: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> str | None:
        for child in root.children:
            if child.type == "package_clause":
                name = self._extract_package_name(child, source)
                if not name:
                    return None
                return self._create_package_symbol(
                    child, name, file_path, file_id, parent_id, nodes, edges, ctx
                )
        return None

    def _extract_package_name(self, node: Any, source: bytes) -> str:
        """Extract package name from a package_clause node."""
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node:
            return node_text(name_node, source)
        # Fallback: search for package_identifier child
        for c in node.children:
            if c.type == "package_identifier":
                return node_text(c, source)
        return ""

    def _create_package_symbol(
        self,
        node: Any,
        name: str,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> str | None:
        """Create and register a package symbol."""
        ls = node_line_start(node)
        le = node_line_end(node)
        qname = name
        sid = make_symbol_id(
            "go", file_path, NodeKind.PACKAGE.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.PACKAGE,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=True,
        )
        if not ctx.inc_symbols():
            return None
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)
        return sid

    def _visit_top(
        self,
        root: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        for child in root.children:
            if not ctx.check_deadline():
                return
            ctx.inc_nodes()
            if child.type == "function_declaration":
                self._handle_func(
                    child, source, file_path, file_id, parent_id, "", nodes, edges, ctx
                )
            elif child.type == "method_declaration":
                self._handle_method(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif child.type == "type_declaration":
                self._handle_type_decl(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif child.type == "import_declaration":
                self._handle_import(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif child.type == "var_declaration":
                self._handle_var(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )

    def _handle_func(
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
    ) -> str | None:
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node is None:
            return None
        name = node_text(name_node, source)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        is_exported = bool(name) and name[0].isupper()
        sid = make_symbol_id("go", file_path, NodeKind.FUNCTION.value, qname, ls, le)
        sig = node_text(node, source).split("{")[0].strip()[:120]
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.FUNCTION,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=le,
            signature=sig,
            parent_id=parent_id,
            is_exported=is_exported,
        )
        if not ctx.inc_symbols():
            return None
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)

        body = (
            node.child_by_field_name("body")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if body:
            self._visit_body(
                body, source, file_path, file_id, sid, qname, nodes, edges, ctx
            )
        return sid

    def _handle_method(
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
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        recv_node = (
            node.child_by_field_name("receiver")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        recv_text = (
            node_text(recv_node, source).strip("()").split()[-1] if recv_node else ""
        )
        qname = f"{recv_text}.{name}" if recv_text else name
        ls = node_line_start(node)
        le = node_line_end(node)
        is_exported = bool(name) and name[0].isupper()
        sid = make_symbol_id("go", file_path, NodeKind.METHOD.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.METHOD,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=is_exported,
            extra={"receiver": recv_text},
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)

    def _handle_type_decl(
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
        for spec in node.children:
            if spec.type != "type_spec":
                continue
            self._process_type_spec(
                spec, source, file_path, file_id, parent_id, nodes, edges, ctx
            )

    def _process_type_spec(
        self,
        spec: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        """Process a single type_spec node."""
        name_node = (
            spec.child_by_field_name("name")
            if hasattr(spec, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        type_node = (
            spec.child_by_field_name("type")
            if hasattr(spec, "child_by_field_name")
            else None
        )
        kind = self._determine_type_kind(type_node)
        self._create_type_symbol(
            spec, name, kind, file_path, file_id, parent_id, nodes, edges, ctx
        )

    def _determine_type_kind(self, type_node: Any) -> NodeKind:
        """Determine the NodeKind based on the type_node."""
        if type_node is None:
            return NodeKind.TYPE
        if type_node.type == "struct_type":
            return NodeKind.STRUCT
        if type_node.type == "interface_type":
            return NodeKind.INTERFACE
        return NodeKind.TYPE

    def _create_type_symbol(
        self,
        spec: Any,
        name: str,
        kind: NodeKind,
        file_path: str,
        file_id: str,
        parent_id: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        """Create and register a type symbol."""
        ls = node_line_start(spec)
        le = node_line_end(spec)
        is_exported = bool(name) and name[0].isupper()
        sid = make_symbol_id("go", file_path, kind.value, name, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=name,
            kind=kind,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=is_exported,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_file_edge(file_id, sid))
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges(2)

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
        for spec in node.children:
            if spec.type not in (
                "import_spec",
                "interpreted_string_literal",
                "raw_string_literal",
            ):
                continue
            path_node = (
                spec.child_by_field_name("path")
                if hasattr(spec, "child_by_field_name")
                else None
            )
            if path_node:
                path_text = node_text(path_node, source).strip('"')
            else:
                path_text = node_text(spec, source).strip('"')
            if not path_text:
                continue
            ls = node_line_start(spec)
            le = node_line_end(spec)
            qname = f"import::{path_text}"
            sid = make_symbol_id("go", file_path, NodeKind.IMPORT.value, qname, ls, le)
            sym = ExtractedNode(
                symbol_id=sid,
                name=path_text,
                qualified_name=qname,
                kind=NodeKind.IMPORT,
                file_path=file_path,
                language="go",
                line_start=ls,
                line_end=le,
                parent_id=parent_id,
            )
            if not ctx.inc_symbols():
                return
            nodes.append(sym)
            edges.append(make_contains_edge(parent_id, sid))
            ctx.inc_edges()

    def _handle_var(
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
        for spec in node.children:
            if spec.type != "var_spec":
                continue
            name_node = (
                spec.child_by_field_name("name")
                if hasattr(spec, "child_by_field_name")
                else None
            )
            if name_node is None:
                continue
            name = node_text(name_node, source)
            if not name or not (name[0].isupper()):
                continue  # only exported vars at package level
            ls = node_line_start(spec)
            le = node_line_end(spec)
            sid = make_symbol_id("go", file_path, NodeKind.VARIABLE.value, name, ls, le)
            sym = ExtractedNode(
                symbol_id=sid,
                name=name,
                qualified_name=name,
                kind=NodeKind.VARIABLE,
                file_path=file_path,
                language="go",
                line_start=ls,
                line_end=le,
                parent_id=parent_id,
                is_exported=True,
            )
            if not ctx.inc_symbols():
                return
            nodes.append(sym)
            ctx.inc_edges()

    def _visit_body(
        self,
        body: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        for child in body.children:
            if not ctx.check_deadline():
                return
            ctx.inc_nodes()
            if child.type == "go_statement":
                self._handle_goroutine(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif child.type == "call_expression":
                self._handle_call(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            else:
                for sub in child.children:
                    if sub.type == "call_expression":
                        self._handle_call(
                            sub,
                            source,
                            file_path,
                            file_id,
                            parent_id,
                            nodes,
                            edges,
                            ctx,
                        )

    def _handle_goroutine(
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
        qname = f"goroutine@{ls}"
        sid = make_symbol_id("go", file_path, NodeKind.GOROUTINE.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=f"goroutine@{ls}",
            qualified_name=qname,
            kind=NodeKind.GOROUTINE,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            capture_reason="go statement",
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
        qname = f"call::{call_name}@{ls}"
        sid = make_symbol_id("go", file_path, NodeKind.CALL.value, qname, ls, ls)
        sym = ExtractedNode(
            symbol_id=sid,
            name=call_name,
            qualified_name=qname,
            kind=NodeKind.CALL,
            file_path=file_path,
            language="go",
            line_start=ls,
            line_end=ls,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(ExtractedEdge(kind=EdgeKind.CALLS, from_id=parent_id, to_id=sid))
        ctx.inc_edges()
