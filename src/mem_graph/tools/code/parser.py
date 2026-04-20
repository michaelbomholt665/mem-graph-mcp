"""
parser.py — MCP tools for tree-sitter parsing and code graph indexing.

Tools:
  parser_health          — Grammar assets, cache sizes, runtime status.
  parse_file             — Parse one file, return parse status (no persist).
  extract_code_symbols   — Parse + extract one file, return symbol summary (no persist).
  index_code_symbols     — Parse + extract + resolve + persist one file.
  index_code_tree        — Index a bounded file tree into Ladybug.

MCP tools call pipeline.py only.  No direct imports from persist.py or ingest.py.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from ..markers import hidden_tool
from pydantic import Field

from ...app.parsers.assets import get_registry
from ...app.parsers.loader import cache_sizes
from ...app.parsers.pipeline import (
    extract_file,
    index_file,
    index_tree,
)
from ...app.parsers.pipeline import (
    parse_file as pipeline_parse_file,
)
from ...app.parsers.types import DEFAULT_LIMITS, ParseLimits
from ...db import db_get_connection

mcp = FastMCP("code", instructions="Tree-sitter code parser and graph indexing tools.")


# ---------------------------------------------------------------------------
# parser_health
# ---------------------------------------------------------------------------


@hidden_tool
def parser_health() -> dict[str, Any]:
    """Report parser assets, caches, and default limits."""
    registry = get_registry()
    health = registry.health()

    per_language: dict[str, dict[str, Any]] = {}
    for lang_key in health["available"]:
        manifest = registry.get(lang_key)
        if manifest:
            per_language[lang_key] = {
                "version": manifest.version,
                "has_binary": manifest.so_path.exists(),
                "has_query": manifest.query_path.exists(),
                "has_node_types": manifest.has_node_types,
                "checksum_ok": manifest.verify_checksum(),
            }

    return {
        "available_languages": health["available"],
        "unavailable": health.get("errors", {}),
        "grammar_root": health["grammar_root"],
        "per_language": per_language,
        "cache_sizes": cache_sizes(),
        "default_limits": {
            "max_file_bytes": DEFAULT_LIMITS.max_file_bytes,
            "max_parse_ms": DEFAULT_LIMITS.max_parse_ms,
            "max_nodes_visited": DEFAULT_LIMITS.max_nodes_visited,
            "max_captures": DEFAULT_LIMITS.max_captures,
            "max_symbols": DEFAULT_LIMITS.max_symbols,
            "max_edges": DEFAULT_LIMITS.max_edges,
            "max_batch_size": DEFAULT_LIMITS.max_batch_size,
        },
    }


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------


@hidden_tool
def parser_parse_file(
    path: Annotated[
        str, Field(description="Absolute or project-relative path to the source file.")
    ],
    language: Annotated[
        str | None,
        Field(
            description="Override language detection. E.g. 'python', 'go', 'typescript'."
        ),
    ] = None,
) -> dict[str, Any]:
    """Parse a file with tree-sitter."""
    result = pipeline_parse_file(path, language=language)
    return {
        "language_key": result.language_key,
        "path": result.path,
        "root_node_type": result.root_node_type,
        "parse_duration_ms": round(result.parse_duration_ms, 2),
        "nodes_visited": result.nodes_visited,
        "has_errors": result.has_errors,
        "error_node_count": result.error_node_count,
        "limit_hit": result.limit_hit,
        "warnings": result.warnings,
    }


# ---------------------------------------------------------------------------
# extract_code_symbols
# ---------------------------------------------------------------------------


@hidden_tool
def extract_code_symbols(
    path: Annotated[
        str, Field(description="Absolute or project-relative path to the source file.")
    ],
    language: Annotated[
        str | None,
        Field(description="Override language detection."),
    ] = None,
    max_symbols: Annotated[
        int,
        Field(
            description="Maximum symbols to extract (default 500, max 5000).",
            ge=1,
            le=5000,
        ),
    ] = 500,
) -> dict[str, Any]:
    """Parse a file and extract its code symbols."""
    limits = ParseLimits(max_symbols=min(max_symbols, DEFAULT_LIMITS.max_symbols))
    parse_result, nodes, edges = extract_file(path, language=language, limits=limits)

    symbol_summary = [
        {
            "name": n.name,
            "kind": n.kind.value,
            "qualified_name": n.qualified_name,
            "line_start": n.line_start,
            "line_end": n.line_end,
            "is_exported": n.is_exported,
            "is_async": n.is_async,
        }
        for n in nodes[:100]  # Cap summary output
    ]

    return {
        "language_key": parse_result.language_key,
        "path": path,
        "parse_duration_ms": round(parse_result.parse_duration_ms, 2),
        "has_errors": parse_result.has_errors,
        "limit_hit": parse_result.limit_hit,
        "warnings": parse_result.warnings,
        "symbol_count": len(nodes),
        "edge_count": len(edges),
        "symbols": symbol_summary,
    }


# ---------------------------------------------------------------------------
# index_code_symbols
# ---------------------------------------------------------------------------


@hidden_tool
def index_code_symbols(
    root: Annotated[
        str,
        Field(
            description="Project root directory (used for relative path computation)."
        ),
    ],
    path: Annotated[
        str, Field(description="Absolute path to the source file to index.")
    ],
) -> dict[str, Any]:
    """Index one file's code symbols into Ladybug."""
    try:
        db_conn = db_get_connection()
        db = db_conn.database
    except RuntimeError as exc:
        return {"success": False, "errors": [str(exc)]}

    result = index_file(
        root=root,
        path=path,
        db=db,
    )
    return {
        "success": result.success,
        "files_written": result.files_written,
        "symbols_written": result.symbols_written,
        "relationships_written": result.relationships_written,
        "stale_cleaned": result.stale_symbols_cleaned,
        "limit_hits": result.limit_hits,
        "errors": result.errors,
        "batches_committed": result.batches_committed,
        "batches_rolled_back": result.batches_rolled_back,
    }


# ---------------------------------------------------------------------------
# index_code_tree
# ---------------------------------------------------------------------------


@hidden_tool
def index_code_tree(
    root: Annotated[str, Field(description="Root directory to index recursively.")],
    include: Annotated[
        list[str] | None,
        Field(description="Glob patterns to include (e.g. ['src/**/*.py', '*.go'])."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        Field(
            description="Glob patterns to exclude (e.g. ['**/test_*.py', 'vendor/**'])."
        ),
    ] = None,
    max_files: Annotated[
        int,
        Field(
            description="Maximum files to index (default 200, max 500).", ge=1, le=500
        ),
    ] = 200,
) -> dict[str, Any]:
    """Index a bounded file tree into Ladybug."""
    try:
        db_conn = db_get_connection()
        db = db_conn.database
    except RuntimeError as exc:
        return {"success": False, "errors": [str(exc)]}

    results = index_tree(
        root=root,
        include=include,
        exclude=exclude,
        db=db,
        max_files=max_files,
    )

    total_files = sum(r.files_written for r in results)
    total_symbols = sum(r.symbols_written for r in results)
    total_rels = sum(r.relationships_written for r in results)
    all_errors = [e for r in results for e in r.errors]
    all_limits = [h for r in results for h in r.limit_hits]

    return {
        "success": len(all_errors) == 0,
        "files_processed": len(results),
        "files_written": total_files,
        "symbols_written": total_symbols,
        "relationships_written": total_rels,
        "limit_hits": all_limits[:20],  # cap output
        "errors": all_errors[:20],
    }
