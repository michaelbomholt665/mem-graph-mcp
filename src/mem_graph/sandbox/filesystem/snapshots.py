"""Repo snapshot, workspace, and merge-back helpers."""

from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path

from ..models.errors import SandboxMergeConflictError, SandboxPolicyError
from ..models.models import SandboxMergeResult

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "build",
    "dist",
    "node_modules",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".lbug",
    ".log",
    ".pyc",
    ".sqlite",
    ".sqlite3",
}
EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".envrc",
    "metadata.json",
}


def session_dir(root: Path, session_id: str) -> Path:
    return root.expanduser().resolve() / "sessions" / session_id


def validate_under_root(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.relative_to(root.expanduser().resolve())
    return resolved


def should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def create_session_layout(root: Path, session_id: str) -> tuple[Path, Path, Path]:
    base = session_dir(root, session_id)
    snapshot = base / "repo"
    workspace = base / "workspace"
    snapshot.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    return base, snapshot, workspace


def create_repo_snapshot(source_root: Path, snapshot_path: Path) -> None:
    source = source_root.expanduser().resolve()
    destination = snapshot_path.expanduser().resolve()
    if source == destination or source in destination.parents:
        raise SandboxPolicyError("Snapshot destination must not be inside source root.")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=_ignore_snapshot_entries)


def initialize_workspace(snapshot_path: Path, workspace_path: Path) -> None:
    snapshot = snapshot_path.expanduser().resolve()
    workspace = workspace_path.expanduser().resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(snapshot, workspace)


def cleanup_session_paths(root: Path, session_id: str) -> None:
    base = validate_under_root(session_dir(root, session_id), root)
    if base.exists():
        shutil.rmtree(base)


def merge_workspace_back(
    *,
    snapshot_path: Path,
    workspace_path: Path,
    host_root: Path,
) -> SandboxMergeResult:
    """Merge changed workspace files into host after conflict checks."""

    snapshot = snapshot_path.expanduser().resolve()
    workspace = workspace_path.expanduser().resolve()
    host = host_root.expanduser().resolve()
    changed: list[str] = []
    conflicts: list[str] = []
    skipped: list[str] = []

    _detect_workspace_changes(workspace, snapshot, host, changed, conflicts, skipped)
    _detect_deleted_files(workspace, snapshot, host, changed, conflicts, skipped)

    if conflicts:
        raise SandboxMergeConflictError(
            "Sandbox merge-back conflicts: " + ", ".join(sorted(conflicts))
        )

    for rel_text in changed:
        rel = Path(rel_text)
        workspace_file = workspace / rel
        host_file = host / rel
        if workspace_file.exists():
            host_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace_file, host_file)
        elif host_file.exists():
            host_file.unlink()

    return SandboxMergeResult(
        status="merged" if changed else "no_changes",
        changed_files=sorted(set(changed)),
        conflicts=[],
        skipped_files=sorted(set(skipped)),
    )


def _detect_workspace_changes(
    workspace: Path,
    snapshot: Path,
    host: Path,
    changed: list[str],
    conflicts: list[str],
    skipped: list[str],
) -> None:
    for workspace_file in _iter_files(workspace):
        rel = workspace_file.relative_to(workspace)
        if should_exclude(rel):
            skipped.append(rel.as_posix())
            continue
        snapshot_file = snapshot / rel
        host_file = host / rel
        workspace_changed = not snapshot_file.exists() or not filecmp.cmp(
            workspace_file, snapshot_file, shallow=False
        )
        if not workspace_changed:
            continue
        host_changed = host_file.exists() and snapshot_file.exists() and not filecmp.cmp(
            host_file, snapshot_file, shallow=False
        )
        if host_changed:
            conflicts.append(rel.as_posix())
            continue
        changed.append(rel.as_posix())


def _detect_deleted_files(
    workspace: Path,
    snapshot: Path,
    host: Path,
    changed: list[str],
    conflicts: list[str],
    skipped: list[str],
) -> None:
    deleted = _deleted_workspace_files(snapshot, workspace)
    for rel in deleted:
        host_file = host / rel
        snapshot_file = snapshot / rel
        if should_exclude(rel):
            skipped.append(rel.as_posix())
            continue
        if host_file.exists() and not filecmp.cmp(host_file, snapshot_file, shallow=False):
            conflicts.append(rel.as_posix())
        else:
            changed.append(rel.as_posix())


def _ignore_snapshot_entries(directory: str, names: list[str]) -> set[str]:
    base = Path(directory)
    ignored: set[str] = set()
    for name in names:
        path = base / name
        rel = path if not path.is_absolute() else Path(*path.parts[-1:])
        if name in EXCLUDED_DIRS or should_exclude(rel):
            ignored.add(name)
    return ignored


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(root)
            if not should_exclude(rel):
                files.append(path)
    return files


def _deleted_workspace_files(snapshot: Path, workspace: Path) -> list[Path]:
    deleted: list[Path] = []
    for snapshot_file in _iter_files(snapshot):
        rel = snapshot_file.relative_to(snapshot)
        if not (workspace / rel).exists():
            deleted.append(rel)
    return deleted
