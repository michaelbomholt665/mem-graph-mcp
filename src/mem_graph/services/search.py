#!/usr/bin/env python3
# src/mem_graph/services/search.py
"""Shared retrieval helpers for hybrid vector and FTS search."""

from __future__ import annotations

from typing import Sequence

_RRF_K = 60


def rrf_fuse(
    vector_hits: Sequence[tuple[str, float]],
    fts_hits: Sequence[tuple[str, float]],
) -> list[tuple[str, float]]:
    """Merge ranked vector and FTS results with Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}

    for rank, (node_id, _) in enumerate(vector_hits, start=1):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (_RRF_K + rank)

    for rank, (node_id, _) in enumerate(fts_hits, start=1):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (_RRF_K + rank)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)