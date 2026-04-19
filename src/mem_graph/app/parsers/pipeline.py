"""
pipeline.py — Orchestration of parse → extract → resolve → ingest.

Public APIs:
  parse_file(path, language=None, limits=None) → ParseResult
  extract_file(path, language=None, limits=None) → (ParseResult, list[ExtractedNode], list[ExtractedEdge])
  index_file(root, path, project_id=None, backend_id=None, limits=None) → PersistenceResult
  index_tree(root, include=None, exclude=None, project_id=None, backend_id=None, limits=None) → list[PersistenceResult]

Rules:
- Calls ingest.py for all persistence at the end of index APIs.
- Never executes DB queries directly.
- Never imports persist.py or ingest.py from MCP tools — only pipeline.py does.
- Returns structured results with counts, warnings, limit hits, and persistence status.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
from pathlib import Path
from typing import Any

from .assets import language_for_path
from .extractors.cypher import CypherExtractor
from .extractors.go import GoExtractor
from .extractors.python import PythonExtractor
from .extractors.sql import SqlExtractor
from .extractors.tsx import TsxExtractor
from .extractors.typescript import TypeScriptExtractor
from .extractors.universal import UNIVERSAL_LANGUAGES, UniversalExtractor
from .loader import parse_bytes
from .persist import build_batch
from .resolvers.anonymous import AnonymousSymbolResolver
from .resolvers.base import build_index
from .resolvers.calls import CallResolver
from .resolvers.go import GoResolver
from .resolvers.imports import ImportResolver
from .resolvers.python import PythonResolver
from .resolvers.query_lineage import QueryLineageResolver
from .resolvers.symbols import SymbolResolver
from .resolvers.typescript import TypeScriptResolver
from .safety import SafetyContext
from .types import (
    DEFAULT_LIMITS,
    ExtractedEdge,
    ExtractedNode,
    ParsedFile,
    ParseLimits,
    ParseResult,
    PersistenceResult,
    ResolutionResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------

_CUSTOM_EXTRACTORS: dict[str, Any] = {
    "python": PythonExtractor(),
    "go": GoExtractor(),
    "typescript": TypeScriptExtractor("typescript"),
    "tsx": TsxExtractor(),
    "cypher": CypherExtractor(),
    "sql": SqlExtractor(),
}

# Universal extractors for config/simple grammars
_UNIVERSAL_EXTRACTORS: dict[str, UniversalExtractor] = {
    lang: UniversalExtractor(lang) for lang in UNIVERSAL_LANGUAGES
}

# ---------------------------------------------------------------------------
# Resolver registry
# ---------------------------------------------------------------------------

_CALL_RESOLVER = CallResolver()
_ANON_RESOLVER = AnonymousSymbolResolver()
_SYMBOL_RESOLVER = SymbolResolver()
_IMPORT_RESOLVER = ImportResolver()


def _build_resolvers(language_key: str, project_root: str | None = None) -> list[Any]:
    resolvers: list[Any] = [
        ImportResolver(project_root),
        _SYMBOL_RESOLVER,
        _CALL_RESOLVER,
        _ANON_RESOLVER,
    ]
    if language_key == "python":
        resolvers.append(PythonResolver())
    elif language_key == "go":
        resolvers.append(GoResolver())
    elif language_key in ("typescript", "tsx"):
        resolvers.append(TypeScriptResolver())
    elif language_key in ("sql", "cypher"):
        resolvers.append(QueryLineageResolver())
    return resolvers


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_file(
    path: str,
    language: str | None = None,
    limits: ParseLimits | None = None,
) -> ParseResult:
    """Parse one file and return parse status only (no extraction)."""
    limits = limits or DEFAULT_LIMITS
    lang = language or language_for_path(path)
    if not lang:
        return ParseResult(
            language_key="unknown",
            path=path,
            root_node_type="",
            parse_duration_ms=0.0,
            nodes_visited=0,
            has_errors=False,
            error_node_count=0,
            warnings=[f"Unsupported file type: {path}"],
        )
    content = _read_file(path)
    if content is None:
        return ParseResult(
            language_key=lang,
            path=path,
            root_node_type="",
            parse_duration_ms=0.0,
            nodes_visited=0,
            has_errors=False,
            error_node_count=0,
            warnings=[f"Cannot read file: {path}"],
        )
    result, _ = parse_bytes(lang, content, limits)
    result.path = path
    return result


def extract_file(
    path: str,
    language: str | None = None,
    limits: ParseLimits | None = None,
) -> tuple[ParseResult, list[ExtractedNode], list[ExtractedEdge]]:
    """Parse and extract one file, returning bounded symbol/edge summaries."""
    limits = limits or DEFAULT_LIMITS
    lang = language or language_for_path(path)
    if not lang:
        pr = ParseResult(
            language_key="unknown",
            path=path,
            root_node_type="",
            parse_duration_ms=0.0,
            nodes_visited=0,
            has_errors=False,
            error_node_count=0,
            warnings=[f"Unsupported file type: {path}"],
        )
        return pr, [], []

    content = _read_file(path)
    if content is None:
        pr = ParseResult(
            language_key=lang,
            path=path,
            root_node_type="",
            parse_duration_ms=0.0,
            nodes_visited=0,
            has_errors=False,
            error_node_count=0,
            warnings=[f"Cannot read file: {path}"],
        )
        return pr, [], []

    parse_result, parsed_file = parse_bytes(lang, content, limits)
    parse_result.path = path

    if parsed_file is None:
        return parse_result, [], []

    parsed_file.path = path
    nodes, edges = _run_extractor(parsed_file, lang, limits)
    return parse_result, nodes, edges


def index_file(
    root: str,
    path: str,
    limits: ParseLimits | None = None,
    db: Any = None,
) -> PersistenceResult:
    """Parse, extract, resolve, and persist one file into Ladybug."""
    limits = limits or DEFAULT_LIMITS

    pr, nodes, edges = extract_file(path, limits=limits)
    if not nodes:
        result = PersistenceResult()
        if pr.warnings:
            result.errors.extend(pr.warnings)
        if pr.limit_hit:
            result.limit_hits.append(pr.limit_hit)
        return result

    lang = pr.language_key
    resolved_edges = _run_resolvers(nodes, edges, path, lang, root)
    all_edges = edges + resolved_edges

    content = _read_file(path) or b""
    file_size = len(content)
    content_hash = hashlib.sha256(content).hexdigest()

    rel_path = _relative_path(root, path)
    batch = build_batch(
        file_path=rel_path,
        language_key=lang,
        nodes=nodes,
        edges=all_edges,
        file_size=file_size,
        content_hash=content_hash,
        max_batch=limits.max_batch_size,
    )

    if db is None:
        result = PersistenceResult()
        result.errors.append("No DB provided — persistence skipped")
        return result

    from .ingest import ingest_batch

    return ingest_batch(db, batch)


def index_tree(
    root: str,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    limits: ParseLimits | None = None,
    db: Any = None,
    max_files: int = 500,
) -> list[PersistenceResult]:
    """Index all supported files under root."""
    results: list[PersistenceResult] = []
    root_path = Path(root)

    if not root_path.is_dir():
        r = PersistenceResult()
        r.errors.append(f"Root directory not found: {root}")
        return [r]

    files = _gather_files(root_path, include, exclude, max_files)
    for file_path in files:
        r = index_file(
            root=root,
            path=str(file_path),
            limits=limits,
            db=db,
        )
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_extractor(
    parsed_file: ParsedFile,
    lang: str,
    limits: ParseLimits,
) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
    ctx = SafetyContext(limits)

    extractor = _CUSTOM_EXTRACTORS.get(lang)
    if extractor is None:
        extractor = _UNIVERSAL_EXTRACTORS.get(lang, UniversalExtractor(lang))

    nodes, edges = extractor.extract(parsed_file, ctx)
    if ctx.limit_hit:
        logger.debug("Extraction limit hit for %s: %s", lang, ctx.limit_hit)
    return nodes, edges


def _run_resolvers(
    nodes: list[ExtractedNode],
    edges: list[ExtractedEdge],
    file_path: str,
    lang: str,
    project_root: str,
) -> list[ExtractedEdge]:
    limits = DEFAULT_LIMITS
    ctx = SafetyContext(limits)
    index = build_index(nodes)
    resolvers = _build_resolvers(lang, project_root)

    all_new_edges: list[ExtractedEdge] = []
    for resolver in resolvers:
        if not ctx.check_deadline():
            break
        res: ResolutionResult = resolver.resolve(
            nodes,
            edges,
            ctx,
            file_path=file_path,
            source=b"",
            language_key=lang,
            index=index,
        )
        all_new_edges.extend(res.resolved_edges)
        if res.limit_hit:
            break

    return all_new_edges


def _read_file(path: str) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def _relative_path(root: str, path: str) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def _should_include_file(
    path: Path,
    root: Path,
    all_extensions: set[str],
    exact_names: set[str],
    include: list[str] | None,
    exclude: list[str] | None,
) -> bool:
    """Check if a file should be included based on extension and filters."""
    name = path.name
    if path.suffix.lower() not in all_extensions and name not in exact_names:
        return False

    if include:
        rel = str(path.relative_to(root))
        if not any(fnmatch.fnmatch(rel, pat) for pat in include):
            return False

    if exclude:
        rel = str(path.relative_to(root))
        if any(fnmatch.fnmatch(rel, pat) for pat in exclude):
            return False

    return True


def _gather_files(
    root: Path,
    include: list[str] | None,
    exclude: list[str] | None,
    max_files: int,
) -> list[Path]:
    from .assets import _FILENAME_TO_LANGUAGE, EXTENSION_TO_LANGUAGE

    results: list[Path] = []
    all_extensions = set(EXTENSION_TO_LANGUAGE.keys())
    exact_names = set(_FILENAME_TO_LANGUAGE.keys())

    for p in root.rglob("*"):
        if len(results) >= max_files:
            break
        if not p.is_file():
            continue
        if _should_include_file(p, root, all_extensions, exact_names, include, exclude):
            results.append(p)

    return results
