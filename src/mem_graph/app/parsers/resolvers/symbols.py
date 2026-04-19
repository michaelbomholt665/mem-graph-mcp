"""
symbols.py — Symbol resolver (inheritance, type references, member resolution).
"""

from __future__ import annotations

import logging

from ..safety import SafetyContext
from ..types import (
    EdgeKind,
    ExtractedEdge,
    ExtractedNode,
    NodeKind,
    ResolutionResult,
)
from .base import BaseResolver

logger = logging.getLogger(__name__)

# Kinds that can be extended or implemented
_INHERITABLE = frozenset({NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.STRUCT})


class SymbolResolver(BaseResolver):
    """Resolves inheritance and interface-implementation edges."""

    def resolve(
        self,
        nodes: list[ExtractedNode],
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
        *,
        file_path: str,
        source: bytes,
        language_key: str,
        index: dict[str, list[ExtractedNode]],
    ) -> ResolutionResult:
        result = ResolutionResult()
        if not ctx.inc_resolver_passes():
            result.limit_hit = ctx.limit_hit
            return result

        for node in nodes:
            if not ctx.check_deadline():
                break
            if node.kind not in _INHERITABLE:
                continue
            self._resolve_extends(node, index, result, ctx)
            self._resolve_implements(node, index, result, ctx)

        return result

    def _resolve_extends(
        self,
        node: ExtractedNode,
        index: dict[str, list[ExtractedNode]],
        result: ResolutionResult,
        ctx: SafetyContext,
    ) -> None:
        """Resolve base class inheritance."""
        for base_name in node.extra.get("extends", []):
            targets = index.get(base_name, [])
            for target in targets[:1]:
                edge = ExtractedEdge(
                    kind=EdgeKind.EXTENDS,
                    from_id=node.symbol_id,
                    to_id=target.symbol_id,
                )
                result.resolved_edges.append(edge)
                ctx.inc_edges()

    def _resolve_implements(
        self,
        node: ExtractedNode,
        index: dict[str, list[ExtractedNode]],
        result: ResolutionResult,
        ctx: SafetyContext,
    ) -> None:
        """Resolve interface implementations."""
        for iface_name in node.extra.get("implements", []):
            targets = index.get(iface_name, [])
            for target in targets[:1]:
                edge = ExtractedEdge(
                    kind=EdgeKind.IMPLEMENTS_SYMBOL,
                    from_id=node.symbol_id,
                    to_id=target.symbol_id,
                )
                result.resolved_edges.append(edge)
                ctx.inc_edges()
