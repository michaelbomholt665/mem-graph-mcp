#!/usr/bin/env python3
"""Graph-enriched file status helpers for the file explorer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Iterable, cast

from pydantic import BaseModel, Field

from ...config import FILE_TREE_DEFAULT_ROOT
from ...db import db_get_connection
from .filesystem import _TAG, mcp

_DONE_STATUSES = {"closed", "done", "resolved"}
_SEVERITY_ORDER = {
    "blocker": 0,
    "critical": 1,
    "major": 2,
    "high": 2,
    "minor": 3,
    "medium": 3,
    "info": 4,
    "low": 4,
}


class FileViolation(BaseModel):
    """Detailed violation metadata for a single file."""

    id: str
    rule: str
    severity: str
    status: str
    description: str
    line_start: int | None = None
    line_end: int | None = None
    detected_at: str | None = None
    last_seen_at: str | None = None


class FileStatus(BaseModel):
    """Graph metadata aggregated for a file-path in the explorer."""

    absolute_path: str
    relative_path: str
    violation_count: int = 0
    violation_types: list[str] = Field(default_factory=list)
    last_audited: str | None = None
    graph_node_id: str | None = None
    violations: list[FileViolation] = Field(default_factory=list)


class FileViolationReport(BaseModel):
    """Detailed response returned to the explorer details pane."""

    file_path: str
    absolute_path: str
    relative_path: str
    total: int
    violation_count: int
    violation_types: list[str] = Field(default_factory=list)
    last_audited: str | None = None
    graph_node_id: str | None = None
    violations: list[FileViolation] = Field(default_factory=list)


def _rows(query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    conn = db_get_connection()
    result = conn.execute(query, params or {})
    if isinstance(result, list):
        result = result[0]
    return cast(list[list[Any]], result.get_all())


def resolve_root_path(*, root_path: str | None = None, project_id: str | None = None) -> Path:
    candidate = root_path or _project_root(project_id) or FILE_TREE_DEFAULT_ROOT or os.getcwd()
    root = Path(candidate).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Root path does not exist or is not a directory: {root}")
    return root


def load_file_status_map(
    *,
    root: Path,
    file_paths: Iterable[Path],
    project_id: str | None = None,
    include_resolved: bool = True,
) -> dict[str, FileStatus]:
    normalized_paths = [path.resolve() for path in file_paths]
    statuses = _init_statuses(root, normalized_paths)
    if not statuses:
        return {}

    alias_map = _build_alias_map(root, normalized_paths)
    _apply_violation_rows(
        statuses,
        alias_map,
        _query_violation_rows(),
        project_id=project_id,
        include_resolved=include_resolved,
    )
    _apply_code_file_rows(statuses, alias_map, _query_code_file_rows(), project_id=project_id)
    _finalize_statuses(statuses.values())
    return statuses


def _init_statuses(root: Path, file_paths: list[Path]) -> dict[str, FileStatus]:
    return {
        str(path): FileStatus(
            absolute_path=str(path),
            relative_path=path.relative_to(root).as_posix(),
        )
        for path in file_paths
    }


def _build_alias_map(root: Path, file_paths: list[Path]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for path in file_paths:
        absolute = str(path)
        relative = path.relative_to(root).as_posix()
        alias_map[absolute] = absolute
        alias_map[relative] = absolute
        alias_map[relative.replace("/", os.sep)] = absolute
    return alias_map


def _query_violation_rows() -> list[list[Any]]:
    return _rows(
        """
        MATCH (v:Violation)
        OPTIONAL MATCH (p:Project)-[:HAS_VIOLATION]->(v)
        RETURN v.id, v.rule, v.severity, v.status, v.file_path,
               v.line_start, v.line_end, v.description, v.detected_at, v.last_seen_at,
               p.id
        ORDER BY v.detected_at DESC
        """
    )


def _query_code_file_rows() -> list[list[Any]]:
    return _rows(
        """
        MATCH (f:CodeFile)
        OPTIONAL MATCH (p:Project)-[:HAS_FILE]->(f)
        RETURN f.id, f.path, f.indexed_at, p.id
        ORDER BY f.indexed_at DESC
        """
    )


def _apply_violation_rows(
    statuses: dict[str, FileStatus],
    alias_map: dict[str, str],
    rows: list[list[Any]],
    *,
    project_id: str | None,
    include_resolved: bool,
) -> None:
    for row in rows:
        absolute_path = alias_map.get(str(row[4] or ""))
        if absolute_path is None or (project_id and row[10] != project_id):
            continue

        violation = _build_violation(row)
        if violation is None:
            continue
        if not include_resolved and violation.status.lower() in _DONE_STATUSES:
            continue

        target = statuses[absolute_path]
        target.violations.append(violation)
        _update_summary_from_violation(target, violation)


def _build_violation(row: list[Any]) -> FileViolation | None:
    violation_id = str(row[0] or "")
    if not violation_id:
        return None
    return FileViolation(
        id=violation_id,
        rule=str(row[1] or ""),
        severity=str(row[2] or "info"),
        status=str(row[3] or "open"),
        description=str(row[7] or ""),
        line_start=int(row[5]) if row[5] is not None else None,
        line_end=int(row[6]) if row[6] is not None else None,
        detected_at=str(row[8]) if row[8] is not None else None,
        last_seen_at=str(row[9]) if row[9] is not None else None,
    )


def _update_summary_from_violation(target: FileStatus, violation: FileViolation) -> None:
    if violation.status.lower() not in _DONE_STATUSES:
        target.violation_count += 1
        if violation.rule and violation.rule not in target.violation_types:
            target.violation_types.append(violation.rule)

    for timestamp in (violation.last_seen_at, violation.detected_at):
        if timestamp and (target.last_audited is None or timestamp > target.last_audited):
            target.last_audited = timestamp


def _apply_code_file_rows(
    statuses: dict[str, FileStatus],
    alias_map: dict[str, str],
    rows: list[list[Any]],
    *,
    project_id: str | None,
) -> None:
    for row in rows:
        absolute_path = alias_map.get(str(row[1] or ""))
        if absolute_path is None or (project_id and row[3] != project_id):
            continue
        target = statuses[absolute_path]
        target.graph_node_id = str(row[0])
        indexed_at = str(row[2]) if row[2] is not None else None
        if indexed_at and (target.last_audited is None or indexed_at > target.last_audited):
            target.last_audited = indexed_at


def _finalize_statuses(statuses: Iterable[FileStatus]) -> None:
    for status in statuses:
        status.violations.sort(
            key=lambda item: (
                _SEVERITY_ORDER.get(item.severity.lower(), 99),
                item.line_start if item.line_start is not None else 10**9,
                item.rule,
            )
        )
        status.violation_types.sort()


def _project_root(project_id: str | None) -> str | None:
    if not project_id:
        return None
    rows = _rows(
        "MATCH (p:Project {id: $project_id}) RETURN p.repo_path LIMIT 1",
        {"project_id": project_id},
    )
    if not rows:
        return None
    repo_path = rows[0][0]
    return str(repo_path) if repo_path else None


@mcp.tool(tags=_TAG)
async def get_file_violations(
    file_path: Annotated[
        str,
        Field(description="Absolute or root-relative file path to inspect."),
    ],
    root_path: Annotated[
        str | None,
        Field(description="Optional root directory used to resolve relative file paths."),
    ] = None,
    project_id: Annotated[
        str | None,
        Field(description="Optional project node ID used to resolve repo_path and filter graph metadata."),
    ] = None,
    include_resolved: Annotated[
        bool,
        Field(description="Include resolved violations as well as currently open ones."),
    ] = True,
) -> FileViolationReport | dict[str, str]:
    """Return detailed violation metadata and last-audited information for a file."""
    try:
        root = resolve_root_path(root_path=root_path, project_id=project_id)
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    resolved_path = Path(file_path)
    if not resolved_path.is_absolute():
        resolved_path = (root / file_path).resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        return {"error": f"File not found: {resolved_path}"}

    statuses = load_file_status_map(
        root=root,
        file_paths=[resolved_path],
        project_id=project_id,
        include_resolved=include_resolved,
    )
    status = statuses[str(resolved_path)]
    return FileViolationReport(
        file_path=file_path,
        absolute_path=status.absolute_path,
        relative_path=status.relative_path,
        total=len(status.violations),
        violation_count=status.violation_count,
        violation_types=status.violation_types,
        last_audited=status.last_audited,
        graph_node_id=status.graph_node_id,
        violations=status.violations,
    )