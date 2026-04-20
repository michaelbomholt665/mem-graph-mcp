"""Tests for the package audit FSM graph."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mem_graph.workflows.runtime.package_audit_runtime import (
    ChunkFinding,
    DiscoverNode,
    PackageAuditDeps,
    PackageAuditReport,
    PackageAuditState,
    _chunk_files,
    _deduplicate_findings,
    _discover_package_files,
    _rank_findings,
    package_audit_graph,
    run_package_audit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_package(num_files: int = 3) -> tuple[Path, Path]:
    """Create a temporary directory with Python files. Returns (tmp_root, pkg_dir)."""
    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "mypkg"
    pkg.mkdir()
    for i in range(num_files):
        (pkg / f"module_{i}.py").write_text(f"# module {i}\n", encoding="utf-8")
    return tmp, pkg


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_discover_package_files_finds_python_files() -> None:
    _, pkg = _make_temp_package(4)
    files = _discover_package_files(str(pkg), [".py"], [])
    assert len(files) == 4
    assert all(f.endswith(".py") for f in files)


def test_discover_package_files_respects_excludes() -> None:
    _, pkg = _make_temp_package(3)
    (pkg / "test_ignored.py").write_text("# test\n", encoding="utf-8")
    files = _discover_package_files(str(pkg), [".py"], ["test_"])
    assert all("test_" not in Path(f).name for f in files)


def test_discover_package_files_missing_dir_returns_empty() -> None:
    files = _discover_package_files("/nonexistent/path/xyz", [".py"], [])
    assert files == []


def test_chunk_files_splits_correctly() -> None:
    files = [f"file_{i}.py" for i in range(7)]
    chunks = _chunk_files(files, 3)
    assert len(chunks) == 3
    assert len(chunks[0]) == 3
    assert len(chunks[2]) == 1


def test_deduplicate_findings_removes_dupes() -> None:
    f1 = ChunkFinding(
        file_path="a.py", rule="R1", severity="high", description="issue X"
    )
    f2 = ChunkFinding(
        file_path="a.py", rule="R1", severity="high", description="issue X"
    )
    result = _deduplicate_findings([f1, f2])
    assert len(result) == 1


def test_rank_findings_orders_by_severity() -> None:
    findings = [
        ChunkFinding(file_path="a.py", rule="R", severity="low", description="d"),
        ChunkFinding(file_path="b.py", rule="R", severity="critical", description="d"),
        ChunkFinding(file_path="c.py", rule="R", severity="medium", description="d"),
    ]
    ranked = _rank_findings(findings)
    assert ranked[0].severity == "critical"
    assert ranked[1].severity == "medium"
    assert ranked[2].severity == "low"


# ---------------------------------------------------------------------------
# FSM graph — dry-run (execute_agents=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_package_audit_graph_dry_run_produces_report() -> None:
    _, pkg = _make_temp_package(5)
    state = PackageAuditState(
        package_paths=[str(pkg)],
        execute_agents=False,
    )
    result = await package_audit_graph.run(DiscoverNode(), state=state)
    report: PackageAuditReport = result.output  # type: ignore[assignment]
    assert isinstance(report, PackageAuditReport)
    assert report.total_packages == 1
    assert report.total_files == 5
    assert report.total_chunks == 1  # 5 files / chunk_size=5


@pytest.mark.asyncio
async def test_package_audit_graph_empty_package_produces_empty_report() -> None:
    _, pkg = _make_temp_package(0)
    state = PackageAuditState(
        package_paths=[str(pkg)],
        execute_agents=False,
    )
    result = await package_audit_graph.run(DiscoverNode(), state=state)
    report: PackageAuditReport = result.output  # type: ignore[assignment]
    assert report.total_packages == 0
    assert report.total_files == 0


@pytest.mark.asyncio
async def test_package_audit_graph_chunks_calculated_correctly() -> None:
    _, pkg = _make_temp_package(12)
    state = PackageAuditState(
        package_paths=[str(pkg)],
        chunk_size=5,
        execute_agents=False,
    )
    result = await package_audit_graph.run(DiscoverNode(), state=state)
    report: PackageAuditReport = result.output  # type: ignore[assignment]
    # 12 files / chunk_size=5 → 3 chunks (5+5+2)
    assert report.total_chunks == 3


# ---------------------------------------------------------------------------
# run_package_audit (backward-compat entry-point)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_package_audit_returns_report() -> None:
    _, pkg = _make_temp_package(3)
    deps = PackageAuditDeps(
        package_paths=[str(pkg)],
        execute_agents=False,
    )
    report = await run_package_audit(deps)
    assert isinstance(report, PackageAuditReport)
    assert report.total_packages == 1


@pytest.mark.asyncio
async def test_run_package_audit_no_packages_returns_empty() -> None:
    deps = PackageAuditDeps(package_paths=[])
    report = await run_package_audit(deps)
    assert report.total_packages == 0
    assert report.total_files == 0


@pytest.mark.asyncio
async def test_run_package_audit_summary_populated() -> None:
    _, pkg = _make_temp_package(2)
    deps = PackageAuditDeps(package_paths=[str(pkg)], execute_agents=False)
    report = await run_package_audit(deps)
    assert report.summary


# ---------------------------------------------------------------------------
# FSM state fields
# ---------------------------------------------------------------------------


def test_package_audit_state_defaults() -> None:
    state = PackageAuditState(package_paths=["./src"])
    assert state.execute_agents is False
    assert state.chunk_size == 5
    assert state.total_chunks_processed == 0
    assert state.report is None


def test_package_audit_report_model() -> None:
    report = PackageAuditReport(
        total_packages=2,
        total_files=10,
        total_chunks=4,
    )
    assert report.total_packages == 2
    assert report.critical_findings == []
    assert report.summary == ""
