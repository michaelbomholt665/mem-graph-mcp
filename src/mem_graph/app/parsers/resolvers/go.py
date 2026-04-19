"""
go.py — Go-specific resolver.

Resolves method→struct containment and goroutine→function containment.
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


class GoResolver(BaseResolver):
    """Go-specific method receiver and goroutine containment resolver."""

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
            if node.kind == NodeKind.METHOD:
                receiver = node.extra.get("receiver", "")
                if receiver:
                    candidates = index.get(receiver, [])
                    struct_nodes = [
                        c
                        for c in candidates
                        if c.kind in (NodeKind.STRUCT, NodeKind.INTERFACE)
                    ]
                    for struct in struct_nodes[:1]:
                        result.resolved_edges.append(
                            ExtractedEdge(
                                kind=EdgeKind.CONTAINS,
                                from_id=struct.symbol_id,
                                to_id=node.symbol_id,
                            )
                        )
                        ctx.inc_edges()

        return result
