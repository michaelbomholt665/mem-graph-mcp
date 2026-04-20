#!/usr/bin/env python3
"""Hierarchical file-tree tool with optional graph metadata enrichment."""

from __future__ import annotations
from ..markers import hidden_tool

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from .status import FileStatus, load_file_status_map, resolve_root_path

_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}


class FileTreeNode(BaseModel):
    """A single node in the file explorer tree."""

    path: str
    relative_path: str
    name: str
    is_dir: bool
    children: list["FileTreeNode"] = Field(default_factory=list)
    violation_count: int = 0
    violation_types: list[str] = Field(default_factory=list)
    last_audited: str | None = None
    graph_node_id: str | None = None


def _sort_entries(entries: list[Path]) -> list[Path]:
    return sorted(
        entries,
        key=lambda item: (not item.is_dir(), item.name.lower(), item.as_posix()),
    )


def _apply_status(
    node: FileTreeNode, status_map: dict[str, FileStatus]
) -> FileTreeNode:
    if not node.is_dir:
        status = status_map.get(node.path)
        if status is None:
            return node
        node.violation_count = getattr(status, "violation_count")
        node.violation_types = list(getattr(status, "violation_types"))
        node.last_audited = getattr(status, "last_audited")
        node.graph_node_id = getattr(status, "graph_node_id")
        return node

    violation_types: set[str] = set()
    last_seen: str | None = None
    total = 0
    for child in node.children:
        _apply_status(child, status_map)
        total += child.violation_count
        violation_types.update(child.violation_types)
        if child.last_audited and (last_seen is None or child.last_audited > last_seen):
            last_seen = child.last_audited
    node.violation_count = total
    node.violation_types = sorted(violation_types)
    node.last_audited = last_seen
    return node


def _should_skip_entry(entry: Path, include_hidden: bool) -> bool:
    if entry.is_symlink():
        return True
    if not include_hidden and entry.name.startswith("."):
        return True
    return entry.is_dir() and entry.name in _SKIP_DIRS


def _visible_entries(path: Path, include_hidden: bool) -> list[Path]:
    try:
        entries = list(path.iterdir())
    except OSError:
        return []
    return [
        entry
        for entry in _sort_entries(entries)
        if not _should_skip_entry(entry, include_hidden)
    ]


def _build_tree(
    *,
    path: Path,
    root: Path,
    include_hidden: bool,
    max_depth: int,
    depth: int,
    files: list[Path],
) -> FileTreeNode:
    relative = "." if path == root else path.relative_to(root).as_posix()
    node = FileTreeNode(
        path=str(path.resolve()),
        relative_path=relative,
        name=path.name if path != root else path.name or str(path),
        is_dir=path.is_dir(),
    )
    if not path.is_dir() or depth >= max_depth:
        if path.is_file():
            files.append(path.resolve())
        return node

    node.children = [
        _build_tree(
            path=entry,
            root=root,
            include_hidden=include_hidden,
            max_depth=max_depth,
            depth=depth + 1,
            files=files,
        )
        for entry in _visible_entries(path, include_hidden)
    ]
    return node


@hidden_tool
async def get_file_tree(
    root_path: Annotated[
        str | None,
        Field(
            description="Optional root directory to explore. Defaults to the project repo_path or current working directory."
        ),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(
            description="Optional project node ID used to resolve repo_path and enrich graph metadata."
        ),
    ] = None,
    include_hidden: Annotated[
        bool,
        Field(description="Include hidden files and directories in the tree."),
    ] = False,
    include_graph_metadata: Annotated[
        bool,
        Field(
            description="Include violation counts, graph node IDs, and last-audited timestamps when available."
        ),
    ] = True,
    max_depth: Annotated[
        int,
        Field(
            description="Maximum depth to traverse from the root directory.",
            ge=1,
            le=16,
        ),
    ] = 8,
) -> FileTreeNode | dict[str, str]:
    """Return a stable, directories-first file tree enriched with violation metadata."""
    try:
        # Automatically resolve repository root from project_id if not provided
        if root_path is None and project_id is not None:
            root = resolve_root_path(project_id=project_id)
        else:
            root = resolve_root_path(root_path=root_path, project_id=project_id)
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    files: list[Path] = []
    tree = _build_tree(
        path=root,
        root=root,
        include_hidden=include_hidden,
        max_depth=max_depth,
        depth=0,
        files=files,
    )

    if include_graph_metadata and files:
        statuses = load_file_status_map(
            root=root, file_paths=files, project_id=project_id
        )
        _apply_status(tree, statuses)

    return tree
