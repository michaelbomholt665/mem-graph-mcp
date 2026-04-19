"""
anonymous.py — Anonymous symbol resolver.

Connects anonymous function symbols (lambdas, closures, goroutines) to
their containing scopes and any call edges that target them.
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

_ANONYMOUS_KINDS = frozenset(
    {
        NodeKind.ANONYMOUS_FUNCTION,
        NodeKind.CLOSURE,
        NodeKind.CALLBACK,
        NodeKind.GOROUTINE,
    }
)


class AnonymousSymbolResolver(BaseResolver):
    """Connects anonymous symbols to their parent scopes."""

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

        anon_nodes = [n for n in nodes if n.kind in _ANONYMOUS_KINDS]

        for anon in anon_nodes:
            if not ctx.check_deadline():
                break
            if anon.parent_id:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.CONTAINS,
                        from_id=anon.parent_id,
                        to_id=anon.symbol_id,
                        props={"anonymous": True},
                    )
                )
                ctx.inc_edges()

        return result
