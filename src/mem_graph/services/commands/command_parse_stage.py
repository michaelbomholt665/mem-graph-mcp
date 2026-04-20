"""Parser staging helpers for curated code parse and watch commands."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...app.parsers.assets import language_for_path
from ...app.parsers.ingest import ingest_batch_data
from ...app.parsers.pipeline import prepare_index_file, prepare_index_tree
from ...app.parsers.types import PersistenceResult, PreparedIndexBatch
from ...db import db_get_connection
from ...services.task_queue import task_queue
from ...tools.background.task_status import build_task_submission
from .base import resolve_root_path

try:
    from watchdog.events import (
        FileSystemEventHandler as _WatchdogFileSystemEventHandler,
    )
    from watchdog.observers import Observer as _WatchdogObserver
except ImportError:  # pragma: no cover - exercised via fallback path
    BaseEventHandler: type[Any] = object
    ObserverFactory: Any = None
else:
    BaseEventHandler = _WatchdogFileSystemEventHandler
    ObserverFactory = _WatchdogObserver


STAGE_DIR = ".mem_graph/parser_stage"


def code_parse(
    *,
    root: str | None = None,
    path: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    max_files: int = 200,
) -> dict[str, Any]:
    """Prepare parser batches without writing them to the graph DB."""
    root_path = resolve_root_path(root)
    if path:
        prepared = prepare_index_file(
            root=str(root_path),
            path=str(_resolve_target_path(root_path, path)),
        )
        return {"mode": "file", "file": _prepared_summary(prepared)}

    prepared_batches = prepare_index_tree(
        root=str(root_path),
        include=include,
        exclude=exclude,
        max_files=max_files,
    )
    return {
        "mode": "tree",
        "files": [_prepared_summary(prepared) for prepared in prepared_batches[:100]],
        "file_count": len(prepared_batches),
    }


def code_stage(
    *,
    root: str | None = None,
    path: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    max_files: int = 200,
) -> dict[str, Any]:
    """Stage prepared parser batches on disk without DB ingest."""
    root_path = resolve_root_path(root)
    stage_root = _stage_root(root_path)
    prepared_batches = (
        [
            prepare_index_file(
                root=str(root_path),
                path=str(_resolve_target_path(root_path, path)),
            )
        ]
        if path
        else prepare_index_tree(
            root=str(root_path),
            include=include,
            exclude=exclude,
            max_files=max_files,
        )
    )

    staged: list[dict[str, Any]] = []
    warnings: list[str] = []
    for prepared in prepared_batches:
        if not prepared.batch_data:
            warnings.extend(prepared.warnings)
            continue
        staged.append(_write_stage_entry(stage_root, prepared))

    return {
        "stage_root": str(stage_root),
        "staged_count": len(staged),
        "staged": staged,
        "warnings": warnings,
    }


def code_commit_index(
    *,
    root: str | None = None,
    relative_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Commit staged parser batches into Ladybug through the ingest boundary."""
    root_path = resolve_root_path(root)
    stage_root = _stage_root(root_path)
    entries = _load_staged_entries(stage_root)
    if relative_paths:
        allowed = set(relative_paths)
        entries = [entry for entry in entries if entry["relative_path"] in allowed]

    conn = db_get_connection()
    db = conn.database
    aggregate = PersistenceResult()
    committed: list[str] = []
    for entry in entries:
        result = ingest_batch_data(db, entry["batch_data"])
        _merge_persistence(aggregate, result)
        if result.success:
            Path(entry["stage_path"]).unlink(missing_ok=True)
            committed.append(entry["relative_path"])

    return {
        "stage_root": str(stage_root),
        "committed": committed,
        "summary": asdict(aggregate),
    }


async def code_watch(
    *,
    root: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    poll_interval: float = 1.0,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Start a background watcher that stages parser batches on file change."""
    warnings: list[str] = []
    if ObserverFactory is None:
        warnings.append("watchdog is not installed; falling back to polling mode.")
    task = await task_queue.enqueue(
        tool_name="code_watch",
        arguments={
            "root": root,
            "include": include or [],
            "exclude": exclude or [],
            "poll_interval": poll_interval,
        },
        session_id=session_id,
        runner=lambda reporter: _watch_worker(
            reporter=reporter,
            root=root,
            include=include,
            exclude=exclude,
            poll_interval=poll_interval,
        ),
    )
    return {"task": build_task_submission(task), "warnings": warnings}


async def _watch_worker(
    *,
    reporter: Any,
    root: str | None,
    include: list[str] | None,
    exclude: list[str] | None,
    poll_interval: float,
) -> dict[str, Any]:
    root_path = resolve_root_path(root)
    await reporter.update(
        5, 100, "watching", f"Watching {root_path} for parser staging changes."
    )
    staged_count = 0

    if ObserverFactory is not None:
        queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        handler = _StageEventHandler(root_path, include, exclude, queue, loop)
        observer = ObserverFactory()
        observer.schedule(handler, str(root_path), recursive=True)
        observer.start()
        try:
            while True:
                changed_path = await queue.get()
                summary = _stage_changed_path(root_path, changed_path)
                if summary is None:
                    continue
                staged_count += 1
                await reporter.update(
                    min(10 + staged_count, 99),
                    100,
                    "watching",
                    f"Staged {summary['relative_path']} from watcher event.",
                )
        finally:
            observer.stop()
            observer.join(timeout=2.0)

    snapshot = _poll_snapshot(root_path, include, exclude)
    while True:
        await asyncio.sleep(poll_interval)
        current = _poll_snapshot(root_path, include, exclude)
        changed = [
            path for path, mtime in current.items() if snapshot.get(path) != mtime
        ]
        snapshot = current
        for changed_path in changed:
            summary = _stage_changed_path(root_path, changed_path)
            if summary is None:
                continue
            staged_count += 1
            await reporter.update(
                min(10 + staged_count, 99),
                100,
                "watching",
                f"Staged {summary['relative_path']} from polling watcher.",
            )


def _stage_changed_path(root_path: Path, changed_path: str) -> dict[str, Any] | None:
    file_path = Path(changed_path)
    if not file_path.exists() or not file_path.is_file():
        return None
    if language_for_path(str(file_path)) is None:
        return None
    prepared = prepare_index_file(root=str(root_path), path=str(file_path.resolve()))
    if not prepared.batch_data:
        return None
    return _write_stage_entry(_stage_root(root_path), prepared)


def _stage_root(root_path: Path) -> Path:
    stage_root = root_path / STAGE_DIR
    stage_root.mkdir(parents=True, exist_ok=True)
    return stage_root


def _resolve_target_path(root_path: Path, path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (root_path / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def _prepared_summary(prepared: PreparedIndexBatch) -> dict[str, Any]:
    return {
        "path": prepared.path,
        "relative_path": prepared.relative_path,
        "language_key": prepared.language_key,
        "node_count": prepared.node_count,
        "edge_count": prepared.edge_count,
        "resolved_edge_count": prepared.resolved_edge_count,
        "warnings": prepared.warnings,
        "limit_hit": prepared.limit_hit,
        "has_batch": bool(prepared.batch_data),
    }


def _write_stage_entry(
    stage_root: Path, prepared: PreparedIndexBatch
) -> dict[str, Any]:
    entry_id = hashlib.sha256(prepared.relative_path.encode("utf-8")).hexdigest()[:16]
    stage_path = stage_root / f"{entry_id}.json"
    payload = {
        "entry_id": entry_id,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "stage_path": str(stage_path),
        **asdict(prepared),
    }
    stage_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return {
        "entry_id": entry_id,
        "relative_path": prepared.relative_path,
        "stage_path": str(stage_path),
        "node_count": prepared.node_count,
        "edge_count": prepared.edge_count,
    }


def _load_staged_entries(stage_root: Path) -> list[dict[str, Any]]:
    if not stage_root.exists():
        return []
    entries = []
    for stage_path in sorted(stage_root.glob("*.json")):
        payload = json.loads(stage_path.read_text(encoding="utf-8"))
        payload["stage_path"] = str(stage_path)
        entries.append(payload)
    return entries


def _merge_persistence(target: PersistenceResult, result: PersistenceResult) -> None:
    target.files_written += result.files_written
    target.symbols_written += result.symbols_written
    target.relationships_written += result.relationships_written
    target.embeddings_written += result.embeddings_written
    target.stale_symbols_cleaned += result.stale_symbols_cleaned
    target.stale_symbols_archived += result.stale_symbols_archived
    target.retries += result.retries
    target.batches_committed += result.batches_committed
    target.batches_rolled_back += result.batches_rolled_back
    target.limit_hits.extend(result.limit_hits)
    target.errors.extend(result.errors)


def _poll_snapshot(
    root_path: Path,
    include: list[str] | None,
    exclude: list[str] | None,
) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for candidate in root_path.rglob("*"):
        if not candidate.is_file() or language_for_path(str(candidate)) is None:
            continue
        rel_path = candidate.relative_to(root_path).as_posix()
        if include and not any(
            fnmatch.fnmatch(rel_path, pattern) for pattern in include
        ):
            continue
        if exclude and any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude):
            continue
        snapshot[str(candidate.resolve())] = candidate.stat().st_mtime_ns
    return snapshot


class _StageEventHandler(BaseEventHandler):
    def __init__(
        self,
        root_path: Path,
        include: list[str] | None,
        exclude: list[str] | None,
        queue: asyncio.Queue[str],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.root_path = root_path
        self.include = include
        self.exclude = exclude
        self.queue = queue
        self.loop = loop

    def on_created(self, event: Any) -> None:
        self._queue_path(
            getattr(event, "src_path", ""),
            is_directory=getattr(event, "is_directory", False),
        )

    def on_modified(self, event: Any) -> None:
        self.on_created(event)

    def on_moved(self, event: Any) -> None:
        self._queue_path(
            getattr(event, "dest_path", ""),
            is_directory=getattr(event, "is_directory", False),
        )

    def _queue_path(self, raw_path: str, *, is_directory: bool) -> None:
        if is_directory or not raw_path:
            return
        path = Path(raw_path)
        if language_for_path(str(path)) is None:
            return
        try:
            rel_path = path.resolve().relative_to(self.root_path).as_posix()
        except ValueError:
            return
        if self.include and not any(
            fnmatch.fnmatch(rel_path, pattern) for pattern in self.include
        ):
            return
        if self.exclude and any(
            fnmatch.fnmatch(rel_path, pattern) for pattern in self.exclude
        ):
            return
        self.loop.call_soon_threadsafe(self.queue.put_nowait, str(path.resolve()))
