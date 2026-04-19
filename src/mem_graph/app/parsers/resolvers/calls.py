"""
calls.py — Call resolver.

Resolves CALL nodes to their definition symbols using a name index.
Emits RESOLVES_TO edges with confidence scores.
"""

from __future__ import annotations

import logging

from ..safety import SafetyContext
from ..types import (
    CallRef,
    EdgeKind,
    ExtractedEdge,
    ExtractedNode,
    NodeKind,
    ResolutionResult,
)
from .base import BaseResolver

logger = logging.getLogger(__name__)

_CALLABLE_KINDS = frozenset(
    {
        NodeKind.FUNCTION,
        NodeKind.METHOD,
        NodeKind.ARROW_FUNCTION,
        NodeKind.CLOSURE,
        NodeKind.ANONYMOUS_FUNCTION,
    }
)


class CallResolver(BaseResolver):
    """Resolves CALL symbols to definition symbols via name index."""

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

        call_nodes = [n for n in nodes if n.kind == NodeKind.CALL]

        for call in call_nodes:
            if not ctx.check_deadline():
                break

            call_name = call.name
            # Strip receiver prefix (e.g. "obj.method" → "method")
            short_name = call_name.rsplit(".", 1)[-1]

            # Try exact match first, then short name
            candidates = index.get(call_name, []) or index.get(short_name, [])
            # Filter to callable kinds
            callable_candidates = [c for c in candidates if c.kind in _CALLABLE_KINDS]

            if callable_candidates:
                target = callable_candidates[0]
                confidence = 0.9 if len(callable_candidates) == 1 else 0.5
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.RESOLVES_TO,
                        from_id=call.symbol_id,
                        to_id=target.symbol_id,
                        props={"confidence": confidence, "resolver": "call_name_index"},
                    )
                )
                ctx.inc_edges()
            else:
                result.unresolved_calls.append(
                    CallRef(
                        from_symbol_id=call.symbol_id,
                        call_name=call_name,
                    )
                )

        return result
