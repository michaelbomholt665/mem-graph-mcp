"""
base.py — Base resolver interface and shared helpers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..safety import SafetyContext
from ..types import (
    ExtractedEdge,
    ExtractedNode,
    ResolutionResult,
)


class BaseResolver(ABC):
    """Abstract base for all resolvers."""

    @abstractmethod
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
        """Produce additional edges from the given node/edge sets."""
        ...


def build_index(nodes: list[ExtractedNode]) -> dict[str, list[ExtractedNode]]:
    """Return a {name → [node]} lookup index."""
    idx: dict[str, list[ExtractedNode]] = {}
    for n in nodes:
        idx.setdefault(n.name, []).append(n)
        idx.setdefault(n.qualified_name, []).append(n)
    return idx
