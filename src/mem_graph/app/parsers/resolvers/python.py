"""
python.py — Python-specific resolver.

Resolves relative imports, qualified names, and decorator edges.
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


class PythonResolver(BaseResolver):
    """Python-specific name and decorator resolution."""

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

        # Resolve method → class containment by qualified name
        for node in nodes:
            if not ctx.check_deadline():
                break
            if node.kind == NodeKind.METHOD and "." in node.qualified_name:
                class_qname = node.qualified_name.rsplit(".", 1)[0]
                candidates = index.get(class_qname, [])
                class_nodes = [c for c in candidates if c.kind == NodeKind.CLASS]
                for cls in class_nodes[:1]:
                    result.resolved_edges.append(
                        ExtractedEdge(
                            kind=EdgeKind.CONTAINS,
                            from_id=cls.symbol_id,
                            to_id=node.symbol_id,
                        )
                    )
                    ctx.inc_edges()

        return result
