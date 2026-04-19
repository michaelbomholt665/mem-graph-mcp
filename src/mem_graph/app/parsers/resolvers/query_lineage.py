"""
query_lineage.py — SQL/Cypher lineage resolver.

Connects SQL table references and CTEs via READS_FROM, ALIASES,
FILTERS_ON, and JOINS_ON edges.
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


class QueryLineageResolver(BaseResolver):
    """Connects SQL/Cypher query nodes with lineage edges."""

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
        if language_key not in ("sql", "cypher"):
            return result
        if not ctx.inc_resolver_passes():
            result.limit_hit = ctx.limit_hit
            return result

        cte_nodes = [n for n in nodes if n.kind == NodeKind.CTE]
        table_nodes = [n for n in nodes if n.kind == NodeKind.TABLE]

        # Connect CTEs to the parent query/statement they belong to
        for cte in cte_nodes:
            if not ctx.check_deadline():
                break
            if cte.parent_id:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.CONTAINS,
                        from_id=cte.parent_id,
                        to_id=cte.symbol_id,
                    )
                )
                ctx.inc_edges()

        # Connect table references to enclosing query
        for tbl in table_nodes:
            if not ctx.check_deadline():
                break
            if tbl.parent_id:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.READS_FROM,
                        from_id=tbl.parent_id,
                        to_id=tbl.symbol_id,
                    )
                )
                ctx.inc_edges()

            # Also check if table name matches a CTE
            cte_matches = [c for c in cte_nodes if c.name == tbl.name]
            for cte in cte_matches[:1]:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.ALIASES,
                        from_id=tbl.symbol_id,
                        to_id=cte.symbol_id,
                    )
                )
                ctx.inc_edges()

        return result
