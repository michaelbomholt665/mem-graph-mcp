"""
assets.py — Grammar asset discovery and validation for the parser pipeline.

Owns:
- Locating grammar directories under data/tree-sitter/grammar/{language}/
- Validating that each grammar has the expected binary, manifest, node-types,
  and query file.
- Reading and caching manifest metadata (no parser execution here).
- File-extension → language-key mapping.

Must not own: parser execution, semantic extraction, DB access.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root directory
# ---------------------------------------------------------------------------

_GRAMMAR_ROOT = Path(__file__).resolve().parents[4] / "data" / "tree-sitter" / "grammar"

# ---------------------------------------------------------------------------
# Supported language keys (order does not matter)
# ---------------------------------------------------------------------------

GO_MOD = "go.mod"
GO_SUM = "go.sum"

SUPPORTED_LANGUAGES: frozenset[str] = frozenset(
    {
        "css",
        "cypher",
        "go",
        GO_MOD,
        GO_SUM,
        "html",
        "java",
        "javascript",
        "json",
        "proto",
        "python",
        "sql",
        "toml",
        "tsx",
        "typescript",
        "yaml",
    }
)

# ---------------------------------------------------------------------------
# Extension → language key mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sql": "sql",
    ".cypher": "cypher",
    ".cql": "cypher",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".proto": "proto",
}

_FILENAME_TO_LANGUAGE: dict[str, str] = {
    GO_MOD: GO_MOD,
    GO_SUM: GO_SUM,
}


def language_for_path(path: str | Path) -> str | None:
    """Return the language key for a file path, or None if unsupported."""
    p = Path(path)
    # Exact filename match first (go.mod, go.sum)
    name = p.name
    if name in _FILENAME_TO_LANGUAGE:
        return _FILENAME_TO_LANGUAGE[name]
    suffix = p.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


# ---------------------------------------------------------------------------
# Grammar manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GrammarManifest:
    """Parsed metadata from manifest.json."""

    language_key: str
    grammar_dir: Path
    so_path: Path
    query_path: Path
    node_types_path: Path
    version: str
    checksum_sha256: str
    has_node_types: bool
    has_queries: bool

    def verify_checksum(self) -> bool:
        """Return True if the binary checksum matches manifest.checksum_sha256."""
        try:
            digest = hashlib.sha256(self.so_path.read_bytes()).hexdigest()
            return digest == self.checksum_sha256
        except OSError:
            return False


# ---------------------------------------------------------------------------
# Asset registry (process-wide, initialized once)
# ---------------------------------------------------------------------------


@dataclass
class _AssetRegistry:
    manifests: dict[str, GrammarManifest] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, compare=False, repr=False
    )
    _loaded: bool = False

    def load_all(self, grammar_root: Path = _GRAMMAR_ROOT) -> None:
        with self._lock:
            if self._loaded:
                return
            self._do_load(grammar_root)
            self._loaded = True

    def _do_load(self, grammar_root: Path) -> None:
        if not grammar_root.is_dir():
            logger.warning("Grammar root not found: %s", grammar_root)
            return
        for lang_key in SUPPORTED_LANGUAGES:
            lang_dir = grammar_root / lang_key
            if not lang_dir.is_dir():
                self.errors[lang_key] = f"Directory not found: {lang_dir}"
                continue
            manifest = _load_manifest(lang_key, lang_dir)
            if isinstance(manifest, str):
                self.errors[lang_key] = manifest
            else:
                self.manifests[lang_key] = manifest

    def get(self, lang_key: str) -> GrammarManifest | None:
        return self.manifests.get(lang_key)

    def available_languages(self) -> list[str]:
        return sorted(self.manifests.keys())

    def health(self) -> dict[str, Any]:
        return {
            "available": self.available_languages(),
            "errors": dict(self.errors),
            "grammar_root": str(_GRAMMAR_ROOT),
        }


_REGISTRY = _AssetRegistry()


def get_registry() -> _AssetRegistry:
    """Return the process-wide asset registry, loading it on first call."""
    _REGISTRY.load_all()
    return _REGISTRY


def get_manifest(lang_key: str) -> GrammarManifest | None:
    """Return the GrammarManifest for a language key, or None."""
    return get_registry().get(lang_key)


# ---------------------------------------------------------------------------
# Internal manifest loader
# ---------------------------------------------------------------------------


def _load_manifest(lang_key: str, lang_dir: Path) -> GrammarManifest | str:
    """Return a GrammarManifest or an error string."""
    manifest_path = lang_dir / "manifest.json"
    if not manifest_path.exists():
        return f"manifest.json missing in {lang_dir}"

    try:
        data = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"Cannot read manifest.json: {exc}"

    binaries: list[dict[str, str]] = data.get("binaries", [])
    if not binaries:
        return "No binaries listed in manifest.json"

    # Pick the first matching binary
    binary = binaries[0]
    so_filename = binary.get("filename", "")
    checksum = binary.get("checksum_sha256", "")
    so_path = lang_dir / so_filename
    if not so_path.exists():
        return f"Binary not found: {so_path}"

    # Query file — name matches language key exactly
    query_filename = f"{lang_key}.scm"
    query_path = lang_dir / "queries" / query_filename
    if not query_path.exists():
        return f"Query file not found: {query_path}"

    # node-types.json (optional but expected)
    node_types_path = lang_dir / "node-types.json"

    artifacts = data.get("artifacts", {})
    return GrammarManifest(
        language_key=lang_key,
        grammar_dir=lang_dir,
        so_path=so_path,
        query_path=query_path,
        node_types_path=node_types_path,
        version=data.get("version", "unknown"),
        checksum_sha256=checksum,
        has_node_types=artifacts.get("has_node_types", False),
        has_queries=artifacts.get("has_queries", False),
    )
