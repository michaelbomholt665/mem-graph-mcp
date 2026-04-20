"""Strict allowlisted command runner for CLI-facing toolchain commands."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from .base import (
    ESCAPE_HATCH_ENV,
    failed,
    ok,
    partial,
    require_gate,
    resolve_root_path,
    trim_text,
)

GO_ALL_PACKAGES = "./..."
CMD_SHELL_EXECUTE = "shell execute"


@dataclass(frozen=True)
class AllowlistedCommand:
    argv: tuple[str, ...]
    optional: bool = False
    timeout_seconds: int = 600


PYTHON_TOOLCHAIN: tuple[AllowlistedCommand, ...] = (
    AllowlistedCommand(("uv", "run", "ruff", "check", "src", "tests", "--fix")),
    AllowlistedCommand(("uv", "run", "mypy", "src")),
    AllowlistedCommand(("uv", "run", "pytest", "-q")),
    AllowlistedCommand(("semgrep", "scan"), optional=True),
    AllowlistedCommand(("trivy", "fs", "."), optional=True),
)

GO_TOOLCHAIN: tuple[AllowlistedCommand, ...] = (
    AllowlistedCommand(("gofumpt", "-w", "."), optional=True),
    AllowlistedCommand(("go", "fmt", GO_ALL_PACKAGES)),
    AllowlistedCommand(("go", "test", GO_ALL_PACKAGES)),
    AllowlistedCommand(("govulncheck", GO_ALL_PACKAGES), optional=True),
    AllowlistedCommand(("trivy", "fs", "."), optional=True),
)

SECURITY_TOOLCHAIN: tuple[AllowlistedCommand, ...] = (
    AllowlistedCommand(("semgrep", "scan"), optional=True),
    AllowlistedCommand(("trivy", "fs", "."), optional=True),
    AllowlistedCommand(("govulncheck", GO_ALL_PACKAGES), optional=True),
)

ALLOWLIST = {
    spec.argv: spec
    for spec in (
        *PYTHON_TOOLCHAIN,
        *GO_TOOLCHAIN,
        *SECURITY_TOOLCHAIN,
    )
}


async def run_allowlisted_command(
    argv: list[str] | tuple[str, ...],
    *,
    root: str | Path | None = None,
    timeout_seconds: int | None = None,
    optional: bool | None = None,
) -> dict[str, Any]:
    """Execute an allowlisted argv tuple without using a shell."""
    command = tuple(argv)
    spec = ALLOWLIST.get(command)
    if spec is None:
        raise ValueError(f"Command is not allowlisted: {' '.join(command)}")

    root_path = resolve_root_path(str(root) if root is not None else None)
    executable = shutil.which(command[0])
    is_optional = spec.optional if optional is None else optional
    if executable is None:
        if is_optional:
            return {
                "argv": list(command),
                "status": "skipped",
                "exit_code": None,
                "timed_out": False,
                "stdout": "",
                "stderr": f"Executable not found: {command[0]}",
                "duration_seconds": 0.0,
            }
        raise FileNotFoundError(f"Executable not found: {command[0]}")

    start = perf_counter()
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(root_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds or spec.timeout_seconds,
        )
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()

    return {
        "argv": list(command),
        "status": "completed"
        if (process.returncode or 0) == 0 and not timed_out
        else "failed",
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "stdout": trim_text(stdout_bytes.decode("utf-8", errors="replace")),
        "stderr": trim_text(stderr_bytes.decode("utf-8", errors="replace")),
        "duration_seconds": round(perf_counter() - start, 4),
    }


async def lint_fix(*, root: str | None = None) -> dict[str, Any]:
    """Run the Python lint subset used by the curated command layer."""
    runs = []
    warnings: list[str] = []
    for spec in PYTHON_TOOLCHAIN[:2]:
        result = await run_allowlisted_command(spec.argv, root=root)
        runs.append(result)
    failures = [
        run for run in runs if run["exit_code"] not in (0, None) or run["timed_out"]
    ]
    if failures:
        return failed(
            "lint fix",
            "One or more lint commands failed.",
            data={"runs": runs},
            warnings=warnings,
        )
    return ok("lint fix", {"runs": runs}, warnings)


async def toolchain_python(*, root: str | None = None) -> dict[str, Any]:
    runs, warnings = await _run_many(PYTHON_TOOLCHAIN, root=root)
    return _summarize_toolchain("toolchain python", runs, warnings)


async def toolchain_go(*, root: str | None = None) -> dict[str, Any]:
    root_path = resolve_root_path(root)
    if not (root_path / "go.mod").exists():
        return failed("toolchain go", f"No go.mod found under {root_path}.")
    runs, warnings = await _run_many(GO_TOOLCHAIN, root=str(root_path))
    return _summarize_toolchain("toolchain go", runs, warnings)


async def toolchain_security(*, root: str | None = None) -> dict[str, Any]:
    root_path = resolve_root_path(root)
    commands = list(SECURITY_TOOLCHAIN)
    if not (root_path / "go.mod").exists():
        commands = [spec for spec in commands if spec.argv[0] != "govulncheck"]
    runs, warnings = await _run_many(tuple(commands), root=str(root_path))
    if not runs:
        return failed(
            "toolchain security", "No security scanners were eligible to run."
        )
    return _summarize_toolchain("toolchain security", runs, warnings)


async def shell_execute(
    argv: list[str],
    *,
    root: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one explicit allowlisted argv tuple behind an environment gate."""
    try:
        require_gate(
            ESCAPE_HATCH_ENV,
            "shell execute is disabled by default.",
        )
    except PermissionError as exc:
        return failed(CMD_SHELL_EXECUTE, str(exc))
    try:
        result = await run_allowlisted_command(
            argv,
            root=root,
            timeout_seconds=timeout_seconds,
        )
    except (FileNotFoundError, ValueError) as exc:
        return failed(CMD_SHELL_EXECUTE, str(exc))
    if result["status"] == "failed":
        return failed(
            CMD_SHELL_EXECUTE, "Allowlisted shell command failed.", data={"run": result}
        )
    if result["status"] == "skipped":
        return partial(CMD_SHELL_EXECUTE, {"run": result}, [result["stderr"]])
    return ok(CMD_SHELL_EXECUTE, {"run": result})


async def _run_many(
    commands: tuple[AllowlistedCommand, ...],
    *,
    root: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    warnings: list[str] = []
    for spec in commands:
        result = await run_allowlisted_command(spec.argv, root=root)
        runs.append(result)
        if result["status"] == "skipped":
            warnings.append(result["stderr"])
    return runs, warnings


def _summarize_toolchain(
    command: str,
    runs: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    failed_runs = [run for run in runs if run["status"] == "failed"]
    if failed_runs:
        return failed(
            command,
            "One or more toolchain steps failed.",
            data={"runs": runs},
            warnings=warnings,
        )
    if warnings:
        return partial(command, {"runs": runs}, warnings)
    return ok(command, {"runs": runs})
