"""
loader.py — Tree-sitter language loading, query compilation, and parse calls.

Owns:
- Loading shared grammar binaries (.so) via ctypes.
- Compiling and caching query files.
- parse_bytes(language_key, content, limits) → ParseResult + ParsedFile.
- Keeping raw Tree-sitter objects (Language, Parser, Tree) behind a thin API.

Must not own: semantic extraction, DB access.
"""

from __future__ import annotations

import ctypes
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from .assets import GrammarManifest, get_manifest
from .safety import SafetyContext, check_file_size
from .types import DEFAULT_LIMITS, ParsedFile, ParseLimits, ParseResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bounded language + query cache
# ---------------------------------------------------------------------------

_MAX_CACHED_LANGUAGES = 32
_MAX_CACHED_QUERIES = 64

_language_cache: dict[str, Any] = {}  # key → tree_sitter.Language
_query_cache: dict[
    tuple[str, str], Any
] = {}  # (lang_key, query_hash) → tree_sitter.Query
_cache_lock = threading.Lock()


def _lang_cache_key(manifest: GrammarManifest) -> str:
    return f"{manifest.language_key}:{manifest.checksum_sha256}"


def _query_cache_key(lang_key: str, query_source: str) -> tuple[str, str]:
    return (lang_key, hashlib.sha256(query_source.encode()).hexdigest()[:16])


# ---------------------------------------------------------------------------
# Language loading
# ---------------------------------------------------------------------------


def _ts_function_name(lang_key: str) -> str:
    """Return the C function name for a language key."""
    safe = lang_key.replace(".", "_").replace("-", "_")
    return f"tree_sitter_{safe}"


def load_language(manifest: GrammarManifest) -> Any:
    """Load and return a tree_sitter.Language for the given manifest."""
    cache_key = _lang_cache_key(manifest)

    with _cache_lock:
        if cache_key in _language_cache:
            return _language_cache[cache_key]

        if len(_language_cache) >= _MAX_CACHED_LANGUAGES:
            # Evict the oldest entry
            oldest = next(iter(_language_cache))
            del _language_cache[oldest]

    try:
        from tree_sitter import Language  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("tree-sitter is not installed") from exc

    fn_name = _ts_function_name(manifest.language_key)
    try:
        lib = ctypes.CDLL(str(manifest.so_path))
        fn = getattr(lib, fn_name)
        fn.restype = ctypes.c_void_p
        language = Language(fn())
    except (OSError, AttributeError) as exc:
        raise RuntimeError(
            f"Cannot load grammar {manifest.language_key!r} from {manifest.so_path}: {exc}"
        ) from exc

    with _cache_lock:
        _language_cache[cache_key] = language
    return language


# ---------------------------------------------------------------------------
# Query compilation
# ---------------------------------------------------------------------------


def load_query(lang_key: str, query_source: str, language: Any) -> Any:
    """Compile and return a tree_sitter.Query, using the cache."""
    ckey = _query_cache_key(lang_key, query_source)

    with _cache_lock:
        if ckey in _query_cache:
            return _query_cache[ckey]

        if len(_query_cache) >= _MAX_CACHED_QUERIES:
            oldest = next(iter(_query_cache))
            del _query_cache[oldest]

    try:
        compiled = language.query(query_source)
    except Exception as exc:
        raise RuntimeError(f"Query compilation failed for {lang_key!r}: {exc}") from exc

    with _cache_lock:
        _query_cache[ckey] = compiled
    return compiled


def load_query_from_manifest(manifest: GrammarManifest, language: Any) -> Any | None:
    """Load the canonical query file for a language, or return None."""
    if not manifest.query_path.exists():
        return None
    try:
        source = manifest.query_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Failed to read tree-sitter query file %s: %s",
            manifest.query_path,
            exc,
        )
        return None
    try:
        return load_query(manifest.language_key, source, language)
    except RuntimeError as exc:
        logger.warning(
            "Failed to compile tree-sitter query for %s: %s",
            manifest.language_key,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Parse call
# ---------------------------------------------------------------------------


@dataclass
class _ParseOutput:
    language: Any
    tree: Any
    manifest: GrammarManifest


def parse_bytes(
    language_key: str,
    content: bytes,
    limits: ParseLimits = DEFAULT_LIMITS,
) -> tuple[ParseResult, ParsedFile | None]:
    """
    Parse *content* for *language_key*.

    Returns (ParseResult, ParsedFile) on success.
    Returns (ParseResult with limit_hit, None) when a safety limit fires.
    """
    # File-size check
    size_err = check_file_size(content, limits)
    if size_err:
        return (
            ParseResult(
                language_key=language_key,
                path="",
                root_node_type="",
                parse_duration_ms=0.0,
                nodes_visited=0,
                has_errors=False,
                error_node_count=0,
                limit_hit=size_err,
            ),
            None,
        )

    manifest = get_manifest(language_key)
    if manifest is None:
        return (
            ParseResult(
                language_key=language_key,
                path="",
                root_node_type="",
                parse_duration_ms=0.0,
                nodes_visited=0,
                has_errors=False,
                error_node_count=0,
                limit_hit=None,
                warnings=[f"No grammar available for {language_key!r}"],
            ),
            None,
        )

    try:
        language = load_language(manifest)
    except RuntimeError as exc:
        return (
            ParseResult(
                language_key=language_key,
                path="",
                root_node_type="",
                parse_duration_ms=0.0,
                nodes_visited=0,
                has_errors=False,
                error_node_count=0,
                warnings=[str(exc)],
            ),
            None,
        )

    from tree_sitter import Parser  # type: ignore[import-untyped]

    ctx = SafetyContext(limits)
    t0 = time.monotonic()
    parser = Parser(language)
    tree = parser.parse(content)
    parse_ms = (time.monotonic() - t0) * 1000

    if parse_ms > limits.max_parse_ms:
        return (
            ParseResult(
                language_key=language_key,
                path="",
                root_node_type=tree.root_node.type,
                parse_duration_ms=parse_ms,
                nodes_visited=0,
                has_errors=tree.root_node.has_error,
                error_node_count=0,
                limit_hit=f"parse_ms>{limits.max_parse_ms}",
            ),
            None,
        )

    # Count nodes and errors (bounded)
    node_count, error_count = _count_nodes(tree.root_node, limits.max_nodes_visited)

    result = ParseResult(
        language_key=language_key,
        path="",
        root_node_type=tree.root_node.type,
        parse_duration_ms=parse_ms,
        nodes_visited=node_count,
        has_errors=tree.root_node.has_error,
        error_node_count=error_count,
        limit_hit=ctx.limit_hit,
    )
    parsed_file = ParsedFile(
        language_key=language_key,
        path="",
        content=content,
        _tree=tree,
        _language=language,
    )
    return result, parsed_file


def _count_nodes(root: Any, max_nodes: int) -> tuple[int, int]:
    """BFS node count; returns (total_visited, error_nodes)."""
    count = 0
    errors = 0
    stack = [root]
    while stack:
        node = stack.pop()
        count += 1
        if count > max_nodes:
            break
        if node.is_error or node.type == "ERROR":
            errors += 1
        stack.extend(node.children)
    return count, errors


# ---------------------------------------------------------------------------
# Cache health
# ---------------------------------------------------------------------------


def cache_sizes() -> dict[str, int]:
    """Return current sizes of language and query caches."""
    with _cache_lock:
        return {
            "languages": len(_language_cache),
            "queries": len(_query_cache),
            "max_languages": _MAX_CACHED_LANGUAGES,
            "max_queries": _MAX_CACHED_QUERIES,
        }


def clear_caches() -> None:
    """Clear all parser caches (for tests)."""
    with _cache_lock:
        _language_cache.clear()
        _query_cache.clear()
