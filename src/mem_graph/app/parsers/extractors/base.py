"""
base.py — Base extractor interface and shared helpers.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

from ..safety import SafetyContext
from ..types import (
    EdgeKind,
    ExtractedEdge,
    ExtractedNode,
    NodeKind,
    ParsedFile,
)


def make_symbol_id(
    language: str,
    file_path: str,
    kind: str,
    qualified_name: str,
    line_start: int,
    line_end: int,
) -> str:
    """Return a deterministic 32-char SHA-256-based ID for a symbol."""
    key = f"{language}:{file_path}:{kind}:{qualified_name}:{line_start}:{line_end}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def make_file_id(relative_path: str) -> str:
    """Return a deterministic 32-char ID for a file path."""
    return hashlib.sha256(relative_path.encode()).hexdigest()[:32]


def node_text(node: Any, source: bytes) -> str:
    """Return the UTF-8 decoded text for a tree-sitter node."""
    try:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def node_line_start(node: Any) -> int:
    """1-indexed start line."""
    return node.start_point[0] + 1


def node_line_end(node: Any) -> int:
    """1-indexed end line."""
    return node.end_point[0] + 1


def make_file_edge(file_id: str, symbol_id: str) -> ExtractedEdge:
    return ExtractedEdge(kind=EdgeKind.FILE_SYMBOL, from_id=file_id, to_id=symbol_id)


def make_contains_edge(parent_id: str, child_id: str) -> ExtractedEdge:
    return ExtractedEdge(kind=EdgeKind.CONTAINS, from_id=parent_id, to_id=child_id)


class BaseExtractor(ABC):
    """Abstract base for all language extractors."""

    @abstractmethod
    def extract(
        self,
        parsed: ParsedFile,
        ctx: SafetyContext,
    ) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
        """Extract symbols and edges from a parsed file."""
        ...

    @property
    @abstractmethod
    def language_key(self) -> str: ...


# ---------------------------------------------------------------------------
# Shared: build a module/file-level root symbol
# ---------------------------------------------------------------------------


def make_file_symbol(
    file_path: str,
    language_key: str,
    line_count: int,
    kind: NodeKind = NodeKind.MODULE,
) -> ExtractedNode:
    """Return a root-level module/file symbol."""
    from ..types import ExtractedNode

    symbol_id = make_symbol_id(
        language=language_key,
        file_path=file_path,
        kind=kind.value,
        qualified_name=file_path,
        line_start=1,
        line_end=line_count,
    )
    name = file_path.rsplit("/", 1)[-1]
    return ExtractedNode(
        symbol_id=symbol_id,
        name=name,
        qualified_name=file_path,
        kind=kind,
        file_path=file_path,
        language=language_key,
        line_start=1,
        line_end=line_count,
        is_exported=True,
    )
