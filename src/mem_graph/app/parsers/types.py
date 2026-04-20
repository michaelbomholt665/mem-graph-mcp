"""
types.py — Stable internal DTOs for the parser pipeline.

All types are independent from Ladybug and FastMCP so extractor, resolver,
persist, and ingest layers can be tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseLimits:
    """Hard caps enforced at every stage of the pipeline."""

    max_file_bytes: int = 512_000  # 512 KB
    max_parse_ms: float = 10_000.0  # 10 s
    max_nodes_visited: int = 100_000
    max_captures: int = 50_000
    max_symbols: int = 5_000
    max_edges: int = 20_000
    max_resolver_passes: int = 3
    max_batch_size: int = 500


DEFAULT_LIMITS = ParseLimits()


# ---------------------------------------------------------------------------
# Symbol kinds
# ---------------------------------------------------------------------------


class NodeKind(str, Enum):
    """Unified kind vocabulary shared by all extractors."""

    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    ARROW_FUNCTION = "arrow_function"
    CLOSURE = "closure"
    ANONYMOUS_FUNCTION = "anonymous_function"
    CALLBACK = "callback"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TYPE = "type"
    IMPORT = "import"
    CALL = "call"
    GOROUTINE = "goroutine"
    DEFER = "defer"
    CHANNEL = "channel"
    DECORATOR = "decorator"
    # Query / SQL / Cypher
    QUERY = "query"
    TABLE = "table"
    COLUMN = "column"
    CTE = "cte"
    ALIAS = "alias"
    LABEL = "label"
    REL_TYPE = "rel_type"
    PARAMETER = "parameter"
    # Generic / config grammars
    ELEMENT = "element"
    ATTRIBUTE = "attribute"
    SECTION = "section"
    KEY = "key"
    VALUE = "value"


class EdgeKind(str, Enum):
    """Relationship types that the parser pipeline emits."""

    FILE_SYMBOL = "FILE_SYMBOL"
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    RESOLVES_TO = "RESOLVES_TO"
    EXTENDS = "EXTENDS"
    IMPLEMENTS_SYMBOL = "IMPLEMENTS_SYMBOL"
    HAS_TYPE = "HAS_TYPE"
    RETURNS_TYPE = "RETURNS_TYPE"
    READS_FROM = "READS_FROM"
    PROJECTS = "PROJECTS"
    FILTERS_ON = "FILTERS_ON"
    JOINS_ON = "JOINS_ON"
    ALIASES = "ALIASES"


# ---------------------------------------------------------------------------
# Request / Result
# ---------------------------------------------------------------------------


@dataclass
class ParseRequest:
    """Input to the parse stage."""

    path: str
    content: bytes
    language_key: str
    limits: ParseLimits = field(default_factory=ParseLimits)
    project_id: str | None = None
    backend_id: str | None = None


@dataclass
class ParseResult:
    """Output of the parse stage — no semantic extraction yet."""

    language_key: str
    path: str
    root_node_type: str
    parse_duration_ms: float
    nodes_visited: int
    has_errors: bool
    error_node_count: int
    limit_hit: str | None = None  # which limit was reached, if any
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    """Opaque handle that carries a parsed tree through the extraction stage.

    Holds the source bytes and a reference to the internal loader result
    without leaking raw Tree-sitter objects to the rest of the pipeline.
    """

    language_key: str
    path: str
    content: bytes
    # raw Tree-sitter tree stored as Any to avoid circular imports
    _tree: Any = field(default=None, repr=False)
    _language: Any = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Extracted nodes and edges
# ---------------------------------------------------------------------------


@dataclass
class ExtractedNode:
    """One semantic symbol produced by an extractor."""

    symbol_id: str  # deterministic sha256-based ID
    name: str
    qualified_name: str
    kind: NodeKind
    file_path: str
    language: str
    line_start: int  # 1-indexed
    line_end: int  # 1-indexed
    signature: str = ""
    parent_id: str | None = None
    is_exported: bool = False
    is_async: bool = False
    display_name: str = ""  # readable label, especially for anonymous symbols
    capture_reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedEdge:
    """One relationship edge produced by an extractor or resolver."""

    kind: EdgeKind
    from_id: str
    to_id: str
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class SymbolRef:
    """A lightweight reference to a symbol for resolver use."""

    symbol_id: str
    qualified_name: str
    name: str
    kind: NodeKind
    file_path: str


@dataclass
class AnonymousSymbol:
    """An anonymous / unnamed symbol (lambda, closure, goroutine, etc.)."""

    symbol_id: str
    kind: NodeKind
    display_name: str
    qualified_name: str
    parent_symbol_id: str
    file_path: str
    language: str
    line_start: int
    line_end: int
    capture_reason: str
    stable_id_key: str


@dataclass
class ImportRef:
    """A parsed import statement."""

    from_symbol_id: str
    module_path: str
    alias: str = ""
    is_relative: bool = False
    resolved_file_id: str | None = None


@dataclass
class CallRef:
    """A call site parsed from source."""

    from_symbol_id: str
    call_name: str
    receiver_name: str = ""
    is_awaited: bool = False
    line: int = 0
    resolved_to_id: str | None = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------


@dataclass
class ResolutionResult:
    """Aggregated result from the resolver stage."""

    resolved_edges: list[ExtractedEdge] = field(default_factory=list)
    unresolved_calls: list[CallRef] = field(default_factory=list)
    unresolved_imports: list[ImportRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limit_hit: str | None = None


# ---------------------------------------------------------------------------
# Prepared index batch
# ---------------------------------------------------------------------------


@dataclass
class PreparedIndexBatch:
    """Serializable parser output that can be staged before DB ingest."""

    root: str
    path: str
    relative_path: str
    language_key: str
    parse_result: ParseResult
    node_count: int = 0
    edge_count: int = 0
    resolved_edge_count: int = 0
    file_size: int = 0
    content_hash: str = ""
    batch_data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    limit_hit: str | None = None


# ---------------------------------------------------------------------------
# Persistence result
# ---------------------------------------------------------------------------


@dataclass
class PersistenceResult:
    """Structured outcome of the ingest stage."""

    files_written: int = 0
    symbols_written: int = 0
    relationships_written: int = 0
    embeddings_written: int = 0
    stale_symbols_cleaned: int = 0
    stale_symbols_archived: int = 0
    limit_hits: list[str] = field(default_factory=list)
    retries: int = 0
    batches_committed: int = 0
    batches_rolled_back: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors and self.batches_rolled_back == 0
