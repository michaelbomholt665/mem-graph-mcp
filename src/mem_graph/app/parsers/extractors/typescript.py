"""
typescript.py — Custom TypeScript extractor.

Produces symbols for: module, function, method, class, interface, type alias,
enum, export, import, variable, arrow function, call, and anonymous symbols.
"""

from __future__ import annotations

import logging
import re
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

_TS_EXTENDS_RE = re.compile(r"\bextends\s+([A-Za-z_$][\w$]*)")
_TS_IMPLEMENTS_RE = re.compile(r"\bimplements\s+([^{]+)")
_TS_NAMED_IMPORT_RE = re.compile(r"\bimport(?:\s+type)?\s*\{([^}]+)\}")
_TS_TYPE_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*")


class TypeScriptExtractor(BaseExtractor):
    """Custom TypeScript extractor."""

    def __init__(self, lang_key: str = "typescript") -> None:
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

        tree = parsed._tree
        source = parsed.content
        file_path = parsed.path

        if tree is None:
            return nodes, edges

        root = tree.root_node
        line_count = root.end_point[0] + 1
        file_id = make_file_id(file_path)

        file_sym = make_file_symbol(
            file_path, self._lang_key, line_count, NodeKind.MODULE
        )
        nodes.append(file_sym)
        edges.append(make_file_edge(file_id, file_sym.symbol_id))
        ctx.inc_symbols()

        self._visit(
            root, source, file_path, file_id, file_sym.symbol_id, "", nodes, edges, ctx
        )
        return nodes, edges

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
            if self._process_child(
                child,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                nodes,
                edges,
                ctx,
            ):
                continue
            # Recursively visit unhandled node types
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

    def _process_child(
        self,
        child: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> bool:
        """Process a child node. Returns True if handled, False otherwise."""
        t = child.type

        if t in ("function_declaration", "generator_function_declaration"):
            self._handle_func(
                child,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                NodeKind.FUNCTION,
                nodes,
                edges,
                ctx,
            )
            return True
        elif t in ("class_declaration", "abstract_class_declaration"):
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
            return True
        elif t == "interface_declaration":
            self._handle_named(
                child,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                NodeKind.INTERFACE,
                nodes,
                edges,
                ctx,
            )
            return True
        elif t == "type_alias_declaration":
            self._handle_named(
                child,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                NodeKind.TYPE,
                nodes,
                edges,
                ctx,
            )
            return True
        elif t == "enum_declaration":
            self._handle_named(
                child,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                NodeKind.ENUM,
                nodes,
                edges,
                ctx,
            )
            return True
        elif t in ("import_statement", "import_declaration"):
            self._handle_import(
                child, source, file_path, file_id, parent_id, nodes, edges, ctx
            )
            return True
        elif t == "export_statement":
            self._handle_export(
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
            return True
        elif t in ("lexical_declaration", "variable_declaration"):
            self._handle_var_decl(
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
            return True
        elif t == "expression_statement":
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
            return True
        elif t == "call_expression":
            self._handle_call(
                child, source, file_path, file_id, parent_id, nodes, edges, ctx
            )
            return True
        return False

    def _handle_func(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        kind: NodeKind,
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
        is_async = any(c.type == "async" for c in node.children)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        sid = make_symbol_id(self._lang_key, file_path, kind.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_async=is_async,
            is_exported=not name.startswith("_"),
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
            self._visit(body, source, file_path, file_id, sid, qname, nodes, edges, ctx)
        return sid

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
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        sid = make_symbol_id(
            self._lang_key, file_path, NodeKind.CLASS.value, qname, ls, le
        )
        class_text = node_text(node, source)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.CLASS,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=not name.startswith("_"),
            extra=self._class_hierarchy(class_text),
        )
        if not ctx.inc_symbols():
            return
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
            for member in body.children:
                mt = member.type
                if mt in ("method_definition", "public_field_definition"):
                    self._handle_method(
                        member,
                        source,
                        file_path,
                        file_id,
                        sid,
                        qname,
                        nodes,
                        edges,
                        ctx,
                    )

    def _class_hierarchy(self, class_text: str) -> dict[str, list[str]]:
        extra: dict[str, list[str]] = {}
        extends_match = _TS_EXTENDS_RE.search(class_text)
        if extends_match:
            extra["extends"] = [extends_match.group(1)]

        implements_match = _TS_IMPLEMENTS_RE.search(class_text)
        if implements_match:
            extra["implements"] = _TS_TYPE_NAME_RE.findall(implements_match.group(1))
        return extra

    def _handle_method(
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
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        is_async = any(c.type == "async" for c in node.children)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        sid = make_symbol_id(
            self._lang_key, file_path, NodeKind.METHOD.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.METHOD,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_async=is_async,
            is_exported=not name.startswith("_"),
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(make_contains_edge(parent_id, sid))
        ctx.inc_edges()

    def _handle_named(
        self,
        node: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        kind: NodeKind,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        name_node = (
            node.child_by_field_name("name")
            if hasattr(node, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        sid = make_symbol_id(self._lang_key, file_path, kind.value, qname, ls, le)
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=not name.startswith("_"),
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
        text = node_text(node, source)
        ls = node_line_start(node)
        le = node_line_end(node)
        imported_names = self._import_names(text) or [text[:80]]
        for name in imported_names:
            qname = f"import::{name}"
            sid = make_symbol_id(
                self._lang_key, file_path, NodeKind.IMPORT.value, qname, ls, le
            )
            sym = ExtractedNode(
                symbol_id=sid,
                name=name,
                qualified_name=qname,
                kind=NodeKind.IMPORT,
                file_path=file_path,
                language=self._lang_key,
                line_start=ls,
                line_end=le,
                parent_id=parent_id,
            )
            if not ctx.inc_symbols():
                return
            nodes.append(sym)
            edges.append(make_contains_edge(parent_id, sid))
            ctx.inc_edges()

    def _import_names(self, import_text: str) -> list[str]:
        match = _TS_NAMED_IMPORT_RE.search(import_text)
        if match is None:
            return []
        names: list[str] = []
        for part in match.group(1).split(","):
            name = part.strip().split(" as ", 1)[0].strip()
            if name:
                names.append(name)
        return names

    def _handle_export(
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
            t = child.type
            if t in ("function_declaration", "generator_function_declaration"):
                self._handle_func(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    NodeKind.FUNCTION,
                    nodes,
                    edges,
                    ctx,
                )
            elif t in ("class_declaration", "abstract_class_declaration"):
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
            elif t in ("lexical_declaration", "variable_declaration"):
                self._handle_var_decl(
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
            elif t == "interface_declaration":
                self._handle_named(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    NodeKind.INTERFACE,
                    nodes,
                    edges,
                    ctx,
                )
            elif t == "type_alias_declaration":
                self._handle_named(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    NodeKind.TYPE,
                    nodes,
                    edges,
                    ctx,
                )
            elif t == "enum_declaration":
                self._handle_named(
                    child,
                    source,
                    file_path,
                    file_id,
                    parent_id,
                    scope_prefix,
                    NodeKind.ENUM,
                    nodes,
                    edges,
                    ctx,
                )

    def _handle_var_decl(
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
        for decl in node.children:
            if decl.type != "variable_declarator":
                continue
            self._process_declarator(
                decl,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                nodes,
                edges,
                ctx,
            )

    def _process_declarator(
        self,
        decl: Any,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        """Process a single variable declarator."""
        name_node = (
            decl.child_by_field_name("name")
            if hasattr(decl, "child_by_field_name")
            else None
        )
        if name_node is None:
            return
        name = node_text(name_node, source)
        val_node = (
            decl.child_by_field_name("value")
            if hasattr(decl, "child_by_field_name")
            else None
        )
        if val_node and val_node.type in (
            "arrow_function",
            "function",
            "function_expression",
        ):
            self._handle_arrow(
                val_node,
                name,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                nodes,
                edges,
                ctx,
            )
        elif name and name[0].isupper():
            self._add_variable_symbol(
                decl,
                name,
                source,
                file_path,
                file_id,
                parent_id,
                scope_prefix,
                nodes,
                edges,
                ctx,
            )

    def _add_variable_symbol(
        self,
        decl: Any,
        name: str,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        """Add a variable symbol to the node list."""
        ls = node_line_start(decl)
        le = node_line_end(decl)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        sid = make_symbol_id(
            self._lang_key, file_path, NodeKind.VARIABLE.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.VARIABLE,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
            parent_id=parent_id,
            is_exported=True,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        ctx.inc_edges()

    def _handle_arrow(
        self,
        node: Any,
        name: str,
        source: bytes,
        file_path: str,
        file_id: str,
        parent_id: str,
        scope_prefix: str,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        is_async = any(c.type == "async" for c in node.children)
        qname = f"{scope_prefix}.{name}" if scope_prefix else name
        ls = node_line_start(node)
        le = node_line_end(node)
        sid = make_symbol_id(
            self._lang_key, file_path, NodeKind.ARROW_FUNCTION.value, qname, ls, le
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=name,
            qualified_name=qname,
            kind=NodeKind.ARROW_FUNCTION,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=le,
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
            if child.type == "call_expression":
                self._handle_call(
                    child, source, file_path, file_id, parent_id, nodes, edges, ctx
                )
            elif child.type in ("await_expression",):
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
        sid = make_symbol_id(
            self._lang_key, file_path, NodeKind.CALL.value, qname, ls, ls
        )
        sym = ExtractedNode(
            symbol_id=sid,
            name=call_name,
            qualified_name=qname,
            kind=NodeKind.CALL,
            file_path=file_path,
            language=self._lang_key,
            line_start=ls,
            line_end=ls,
            parent_id=parent_id,
        )
        if not ctx.inc_symbols():
            return
        nodes.append(sym)
        edges.append(ExtractedEdge(kind=EdgeKind.CALLS, from_id=parent_id, to_id=sid))
        ctx.inc_edges()
