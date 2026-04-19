"""
imports.py — Import resolver.

Resolves import symbols in the extracted node set to existing CodeFile or
module symbols within the indexed project root.
"""

from __future__ import annotations

import logging
from pathlib import Path

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

_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
_PY_EXTENSIONS = (".py",)


class ImportResolver(BaseResolver):
    """Resolves import nodes to file symbols in the index root."""

    def __init__(self, project_root: str | None = None) -> None:
        self._root = Path(project_root) if project_root else None

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

        import_nodes = [n for n in nodes if n.kind == NodeKind.IMPORT]
        if not import_nodes:
            return result

        if not ctx.inc_resolver_passes():
            result.limit_hit = ctx.limit_hit
            return result

        for imp in import_nodes:
            if not ctx.check_deadline():
                break
            self._resolve_one(imp, file_path, language_key, index, result, edges, ctx)

        return result

    def _resolve_one(
        self,
        imp: ExtractedNode,
        file_path: str,
        language_key: str,
        index: dict[str, list[ExtractedNode]],
        result: ResolutionResult,
        edges: list[ExtractedEdge],
        ctx: SafetyContext,
    ) -> None:
        module_path = imp.name
        candidates = index.get(module_path, [])
        if candidates:
            for candidate in candidates[:1]:
                edge = ExtractedEdge(
                    kind=EdgeKind.IMPORTS,
                    from_id=imp.symbol_id,
                    to_id=candidate.symbol_id,
                    props={
                        "module_path": module_path,
                        "alias": "",
                        "is_relative": False,
                    },
                )
                result.resolved_edges.append(edge)
                ctx.inc_edges()
            return

        # Try resolving relative imports via filesystem
        if self._root is not None and (
            module_path.startswith(".") or language_key in ("python",)
        ):
            resolved = self._resolve_file(file_path, module_path, language_key)
            if resolved:
                result.resolved_edges.append(
                    ExtractedEdge(
                        kind=EdgeKind.IMPORTS,
                        from_id=imp.symbol_id,
                        to_id=_file_id(resolved),
                        props={
                            "module_path": resolved,
                            "alias": "",
                            "is_relative": True,
                        },
                    )
                )
                ctx.inc_edges()
                return

        # Unresolved external
        from ..types import ImportRef

        result.unresolved_imports.append(
            ImportRef(from_symbol_id=imp.symbol_id, module_path=module_path)
        )

    def _resolve_file(self, from_path: str, module: str, lang: str) -> str | None:
        if self._root is None:
            return None
        base = self._root / from_path
        parent = base.parent if not base.is_dir() else base

        if lang == "python":
            return self._resolve_python_file(parent, module)
        elif lang in ("typescript", "tsx", "javascript"):
            return self._resolve_typescript_file(parent, module)
        return None

    def _resolve_python_file(self, parent: Path, module: str) -> str | None:
        """Resolve a Python module file."""
        if self._root is None:
            return None
        rel = module.replace(".", "/")
        for ext in _PY_EXTENSIONS:
            candidate = parent / f"{rel}{ext}"
            if candidate.exists():
                return str(candidate.relative_to(self._root))
        candidate = parent / rel / "__init__.py"
        if candidate.exists():
            return str(candidate.relative_to(self._root))
        return None

    def _resolve_typescript_file(self, parent: Path, module: str) -> str | None:
        """Resolve a TypeScript/JavaScript module file."""
        if self._root is None:
            return None
        rel = module.lstrip("./")
        for ext in _TS_EXTENSIONS:
            candidate = parent / f"{rel}{ext}"
            if candidate.exists():
                return str(candidate.relative_to(self._root))
        for ext in _TS_EXTENSIONS:
            candidate = parent / rel / f"index{ext}"
            if candidate.exists():
                return str(candidate.relative_to(self._root))
        return None


def _file_id(path: str) -> str:
    import hashlib

    return hashlib.sha256(path.encode()).hexdigest()[:32]
