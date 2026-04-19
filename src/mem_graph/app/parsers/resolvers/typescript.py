"""
typescript.py — TypeScript-specific resolver.

Resolves arrow functions, class member inheritance, and import aliases.
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


class TypeScriptResolver(BaseResolver):
    """TypeScript class hierarchy and member resolution."""

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
            if node.kind not in (NodeKind.CLASS, NodeKind.INTERFACE):
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
            candidates = index.get(base_name, [])
            for target in candidates[:1]:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.EXTENDS,
                        from_id=node.symbol_id,
                        to_id=target.symbol_id,
                    )
                )
                ctx.inc_edges()

    def _resolve_implements(
        self,
        node: ExtractedNode,
        index: dict[str, list[ExtractedNode]],
        result: ResolutionResult,
        ctx: SafetyContext,
    ) -> None:
        """Resolve interface implementations."""
        for iface in node.extra.get("implements", []):
            candidates = index.get(iface, [])
            for target in candidates[:1]:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.IMPLEMENTS_SYMBOL,
                        from_id=node.symbol_id,
                        to_id=target.symbol_id,
                    )
                )
                ctx.inc_edges()
