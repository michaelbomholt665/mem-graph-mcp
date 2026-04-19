#!/usr/bin/env python3
# src/mem_graph/workflows/runtime/package_audit_runtime.py
"""
Iterative Package Audit Runtime.

Processes a codebase package-by-package, reading 4-5 files per chunk.
For each chunk: read/analyze files, produce findings, update a running
report. Continues until all packages are covered, then deduplicates
findings and re-ranks severity globally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...resources.workflows.selector import select_all
from .workflow_sandbox import (
    abort_workflow_sandbox,
    ensure_workflow_sandbox,
    finalize_workflow_sandbox,
)

logger = logging.getLogger(__name__)

################
#   CONSTANTS
################

_DEFAULT_CHUNK_SIZE = 5
_MAX_FILE_BYTES = 64_000

################
#   MODELS
################


class ChunkFinding(BaseModel):
    """A single finding from a file chunk analysis."""

    file_path: str = Field(description="Source file this finding applies to.")
    rule: str = Field(description="Rule or check that triggered this finding.")
    severity: str = Field(
        default="medium",
        description="Severity level: critical, high, medium, low, info.",
    )
    description: str = Field(description="Human-readable finding description.")
    line_number: int | None = Field(
        default=None,
        description="Approximate line number, if available.",
    )


class PackageSummary(BaseModel):
    """Consolidated findings for one package after all its chunks are processed."""

    package: str = Field(description="Package name or path.")
    file_count: int = Field(description="Total files audited in this package.")
    chunk_count: int = Field(description="Number of chunks processed.")
    findings: list[ChunkFinding] = Field(default_factory=list)
    notes: str = Field(default="", description="Agent notes for this package.")


class PackageAuditReport(BaseModel):
    """Final deduped, re-ranked report across all packages."""

    total_packages: int = Field(description="Number of packages audited.")
    total_files: int = Field(description="Total files read across all packages.")
    total_chunks: int = Field(description="Total chunks processed.")
    packages: list[PackageSummary] = Field(default_factory=list)
    critical_findings: list[ChunkFinding] = Field(default_factory=list)
    high_findings: list[ChunkFinding] = Field(default_factory=list)
    medium_findings: list[ChunkFinding] = Field(default_factory=list)
    low_findings: list[ChunkFinding] = Field(default_factory=list)
    follow_up_items: list[str] = Field(
        default_factory=list,
        description="Unresolved items requiring further investigation.",
    )
    summary: str = Field(default="", description="Executive summary.")


################
#   DEPS
################


@dataclass
class PackageAuditDeps:
    """Dependencies for the package audit runtime."""

    package_paths: list[str]
    """List of package directories to audit."""

    file_extensions: list[str] = field(default_factory=lambda: [".py"])
    """File extensions to include."""

    chunk_size: int = _DEFAULT_CHUNK_SIZE
    """Files per chunk (recommended: 4-5)."""

    exclude_patterns: list[str] = field(
        default_factory=lambda: ["__pycache__", ".pyc", "test_", "_test.py"]
    )
    """Glob/substring patterns to exclude from the file list."""

    extra_context: dict[str, Any] = field(default_factory=dict)
    """Optional extra context passed to the analyzer."""

    execute_agents: bool = False
    """Whether to invoke real audit sub-agents (vs. dry-run structure)."""


################
#   FILE DISCOVERY
################


def _discover_package_files(
    package_path: str,
    extensions: list[str],
    exclude_patterns: list[str],
) -> list[str]:
    """Return sorted list of in-scope file paths within a package directory."""
    root = Path(package_path)
    if not root.exists():
        return []

    files: list[str] = []
    for ext in extensions:
        for path in sorted(root.rglob(f"*{ext}")):
            filename = path.name
            if any(pattern in filename for pattern in exclude_patterns):
                continue
            files.append(str(path))
    return files


def _chunk_files(files: list[str], chunk_size: int) -> list[list[str]]:
    """Split a file list into chunks of at most chunk_size."""
    return [files[i : i + chunk_size] for i in range(0, len(files), chunk_size)]


################
#   FILE READING
################


def _read_files_async(file_paths: list[str]) -> dict[str, str]:
    """Read a list of files asynchronously, truncating at _MAX_FILE_BYTES."""
    contents: dict[str, str] = {}
    for path in file_paths:
        try:
            raw = Path(path).read_bytes()
            if len(raw) > _MAX_FILE_BYTES:
                contents[path] = (
                    raw[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
                    + "\n[TRUNCATED]"
                )
            else:
                contents[path] = raw.decode("utf-8", errors="replace")
        except Exception as exc:
            contents[path] = f"ERROR: {exc}"
    return contents


################
#   CHUNK ANALYSIS
################


async def _analyze_chunk(
    chunk: list[str],
    file_contents: dict[str, str],
    package: str,
    *,
    execute_agents: bool,
) -> list[ChunkFinding]:
    """Analyze a single chunk of files and return findings.

    When execute_agents is True, delegates to the audit agent.
    Otherwise returns an empty findings list (dry-run for testing).
    """
    if not execute_agents:
        return []

    try:
        from ...agents.audit.audit_agent import AuditDependencies, preloaded_audit_agent

        formatted = "\n\n".join(
            f"### {path}\n```\n{content}\n```"
            for path, content in file_contents.items()
        )
        deps = AuditDependencies(
            package_path=package,
            extra_file_context=formatted,
        )
        result = await preloaded_audit_agent.run(
            f"Audit this chunk of {len(chunk)} file(s) from package '{package}'. "
            "Return an AuditReport with all findings.",
            deps=deps,
        )
        report = result.output
        findings: list[ChunkFinding] = []
        for violation in getattr(report, "violations", []):
            findings.append(
                ChunkFinding(
                    file_path=getattr(
                        violation, "file_path", chunk[0] if chunk else ""
                    ),
                    rule=getattr(violation, "rule", "unknown"),
                    severity=getattr(violation, "severity", "medium"),
                    description=getattr(violation, "description", str(violation)),
                )
            )
        return findings
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chunk analysis failed for %s: %s", package, exc)
        return []


################
#   DEDUPLICATION
################


def _deduplicate_findings(findings: list[ChunkFinding]) -> list[ChunkFinding]:
    """Deduplicate findings by (file_path, rule, description) key."""
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ChunkFinding] = []
    for f in findings:
        key = (f.file_path, f.rule, f.description[:100])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _rank_findings(findings: list[ChunkFinding]) -> list[ChunkFinding]:
    """Sort findings by severity from most to least severe."""
    return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 5))


################
#   MAIN RUNTIME
################


async def run_package_audit(deps: PackageAuditDeps) -> PackageAuditReport:
    """
    Run the iterative package audit across all given package paths.

    For each package:
    1. Discover in-scope files.
    2. Split into chunks of deps.chunk_size.
    3. For each chunk: read files, analyze, accumulate findings.
    4. Close package summary.

    After all packages:
    5. Deduplicate findings across packages.
    6. Re-rank severity globally.
    7. Produce the final PackageAuditReport.

    Args:
        deps: PackageAuditDeps with package paths and configuration.

    Returns:
        PackageAuditReport with deduped, ranked findings.
    """
    selection = select_all("package_audit", file_count=0, preferred_key="package_audit")
    sandbox = (
        await ensure_workflow_sandbox(
            selection,
            {"package_paths": deps.package_paths},
        )
        if deps.execute_agents
        else None
    )

    try:
        return await _run_package_audit_inner(
            deps,
            sandbox_artifact=sandbox.artifact() if sandbox else {},
        )
    except Exception:
        if sandbox is not None:
            await abort_workflow_sandbox(sandbox)
        raise
    finally:
        if sandbox is not None:
            await finalize_workflow_sandbox(sandbox, validation_passed=False)


async def _run_package_audit_inner(
    deps: PackageAuditDeps,
    *,
    sandbox_artifact: dict[str, Any],
) -> PackageAuditReport:
    del sandbox_artifact
    all_findings: list[ChunkFinding] = []
    package_summaries: list[PackageSummary] = []
    total_files = 0
    total_chunks = 0

    for pkg_path in deps.package_paths:
        logger.info("[PACKAGE AUDIT] Processing package: %s", pkg_path)
        pkg_files = _discover_package_files(
            pkg_path,
            deps.file_extensions,
            deps.exclude_patterns,
        )
        if not pkg_files:
            logger.info("[PACKAGE AUDIT] No files found in %s — skipping.", pkg_path)
            continue

        chunks = _chunk_files(pkg_files, deps.chunk_size)
        pkg_findings: list[ChunkFinding] = []

        for chunk_idx, chunk in enumerate(chunks):
            logger.info(
                "[PACKAGE AUDIT] %s chunk %d/%d (%d file(s))",
                pkg_path,
                chunk_idx + 1,
                len(chunks),
                len(chunk),
            )
            file_contents = _read_files_async(chunk)
            chunk_findings = await _analyze_chunk(
                chunk,
                file_contents,
                pkg_path,
                execute_agents=deps.execute_agents,
            )
            pkg_findings.extend(chunk_findings)
            total_chunks += 1

        total_files += len(pkg_files)
        all_findings.extend(pkg_findings)
        package_summaries.append(
            PackageSummary(
                package=pkg_path,
                file_count=len(pkg_files),
                chunk_count=len(chunks),
                findings=pkg_findings,
            )
        )

    # Finalize: deduplicate and re-rank globally
    deduped = _deduplicate_findings(all_findings)
    ranked = _rank_findings(deduped)

    by_severity: dict[str, list[ChunkFinding]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }
    follow_up: list[str] = []
    for finding in ranked:
        sev = finding.severity
        if sev in by_severity:
            by_severity[sev].append(finding)
        if sev in {"critical", "high"}:
            follow_up.append(
                f"{sev.upper()}: {finding.rule} in {finding.file_path} — "
                f"{finding.description[:120]}"
            )

    pkg_count = len(package_summaries)
    critical_count = len(by_severity["critical"])
    high_count = len(by_severity["high"])
    total_issues = len(ranked)
    summary = (
        f"Audited {pkg_count} package(s), {total_files} file(s) in {total_chunks} chunk(s). "
        f"Found {total_issues} unique issue(s): "
        f"{critical_count} critical, {high_count} high."
    )

    return PackageAuditReport(
        total_packages=pkg_count,
        total_files=total_files,
        total_chunks=total_chunks,
        packages=package_summaries,
        critical_findings=by_severity["critical"],
        high_findings=by_severity["high"],
        medium_findings=by_severity["medium"],
        low_findings=by_severity["low"],
        follow_up_items=follow_up[:50],
        summary=summary,
    )
