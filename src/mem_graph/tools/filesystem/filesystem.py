#!/usr/bin/env python3

"""
tools/filesystem/filesystem.py — Core filesystem manipulation tools for CodeMode.

Six tools expose controlled filesystem access so the AI can read, search,
and surgically edit files during CodeMode code-generation sessions.

All tools are tagged ``namespace:filesystem`` and disabled at startup.
Activate with ``tools_activate(namespace='filesystem')``.

Security: these tools operate on the local filesystem with the permissions
of the MCP server process. Do not expose this server on an untrusted network.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
from typing import Annotated

import anyio
from fastmcp import FastMCP
from pydantic import Field

logger = logging.getLogger(__name__)
mcp = FastMCP("filesystem", instructions="Core filesystem read, search, and edit tools.")

_TAG = {"namespace:filesystem"}


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_read(
    path: Annotated[str, Field(description="Absolute path to the file to read.")],
    start_line: Annotated[int, Field(description="First line to return (1-indexed). Defaults to 1.", ge=1)] = 1,
    end_line: Annotated[int | None, Field(description="Last line to return (inclusive). Omit for full file.")] = None,
) -> dict:
    """
    Read and return the contents of a source file, optionally limited to a line range.

    Provide an absolute path and optional start/end lines to read a specific block.
    Returns the file content and total line count. Use for code inspection during audits.
    """
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}

    try:
        async with await anyio.open_file(path, "r", encoding="utf-8", errors="replace") as f:
            lines = await f.readlines()
    except OSError as exc:
        return {"error": f"Cannot read file: {exc}"}

    total = len(lines)
    lo = start_line - 1
    hi = end_line if end_line is not None else total
    hi = min(hi, total)
    selected = lines[lo:hi]
    return {
        "path": path,
        "content": "".join(selected),
        "start_line": start_line,
        "end_line": lo + len(selected),
        "total_lines": total,
    }


# ---------------------------------------------------------------------------
# file_search
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_search(
    directory: Annotated[str, Field(description="Absolute path to the root directory to search.")],
    pattern: Annotated[str, Field(description="Filename glob pattern, e.g. '*.py' or 'main.go'.")],
    max_results: Annotated[int, Field(description="Maximum number of file paths to return.", ge=1, le=500)] = 100,
) -> dict:
    """
    Search and list files matching a glob pattern within a directory tree.

    Provide a root directory and a filename pattern to locate source files, config files,
    or any file type. Returns matched paths sorted alphabetically. Useful before file_read.
    """
    if not os.path.isdir(directory):
        return {"error": f"Directory not found: {directory}"}

    matches: list[str] = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                matches.append(os.path.join(root, name))
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    matches.sort()
    return {"matches": matches, "count": len(matches), "truncated": len(matches) >= max_results}


# ---------------------------------------------------------------------------
# file_grep
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_grep(
    directory: Annotated[str, Field(description="Absolute path to the root directory to search.")],
    pattern: Annotated[str, Field(description="Text or regex pattern to search for across files.")],
    file_glob: Annotated[str, Field(description="File glob filter, e.g. '*.py'. Defaults to '*'.")] = "*",
    is_regex: Annotated[bool, Field(description="Treat pattern as a regex. Defaults to False (literal match).")] = False,
    max_results: Annotated[int, Field(description="Maximum number of match lines to return.", ge=1, le=1000)] = 200,
) -> dict:
    """
    Search and find text or regex patterns across source files in a directory tree.

    Provide a root directory, a search pattern, and an optional file glob filter.
    Returns matching lines with file path and line number. Use for code discovery and audits.
    """
    if not os.path.isdir(directory):
        return {"error": f"Directory not found: {directory}"}

    compiled = _compile_pattern(pattern, is_regex)
    if compiled is None:
        return {"error": f"Invalid regex pattern: {pattern!r}"}

    results: list[dict] = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if not fnmatch.fnmatch(name, file_glob):
                continue
            file_path = os.path.join(root, name)
            found = await _grep_file(file_path, compiled, max_results - len(results))
            results.extend(found)
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    return {"matches": results, "count": len(results), "truncated": len(results) >= max_results}


def _compile_pattern(pattern: str, is_regex: bool) -> re.Pattern[str] | None:
    if is_regex:
        try:
            return re.compile(pattern)
        except re.error:
            return None
    return re.compile(re.escape(pattern))


async def _grep_file(path: str, compiled: re.Pattern[str], limit: int) -> list[dict]:
    results: list[dict] = []
    try:
        async with await anyio.open_file(path, "r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(await f.readlines(), start=1):
                if compiled.search(line):
                    results.append({"path": path, "line": lineno, "content": line.rstrip("\n")})
                if len(results) >= limit:
                    break
    except OSError:
        pass
    return results


# ---------------------------------------------------------------------------
# file_write
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_write(
    path: Annotated[str, Field(description="Absolute path to the file to create or overwrite.")],
    content: Annotated[str, Field(description="Full file content to write.")],
) -> dict:
    """
    Create or overwrite a file with the given content.

    Provide the absolute path and the complete content string. Parent directories
    must already exist. Overwrites existing files without confirmation — use carefully.
    Returns confirmation with byte count written.
    """
    if not os.path.isdir(os.path.dirname(path) or "."):
        return {"error": f"Parent directory does not exist for: {path}"}

    try:
        async with await anyio.open_file(path, "w", encoding="utf-8") as f:
            await f.write(content)
    except OSError as exc:
        return {"error": f"Cannot write file: {exc}"}

    logger.info("file_write: wrote %d bytes to %s", len(content), path)
    return {"path": path, "bytes_written": len(content.encode("utf-8")), "status": "ok"}


# ---------------------------------------------------------------------------
# file_edit
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_edit(
    path: Annotated[str, Field(description="Absolute path to the file to edit.")],
    old_text: Annotated[str, Field(description="Exact text block to replace. Must appear exactly once in the file.")],
    new_text: Annotated[str, Field(description="Replacement text block.")],
) -> dict:
    """
    Surgically replace one exact block of text inside a file.

    Provide the file path, the exact text to find, and the replacement. The old_text
    must appear exactly once in the file or the edit is rejected. Use file_read first
    to capture the exact text before calling this tool.
    """
    if not os.path.isfile(path):
        return {"error": f"File not found: {path}"}

    try:
        async with await anyio.open_file(path, "r", encoding="utf-8", errors="replace") as f:
            original = await f.read()
    except OSError as exc:
        return {"error": f"Cannot read file: {exc}"}

    count = original.count(old_text)
    if count == 0:
        return {"error": "old_text not found in file — verify the exact text using file_read first."}
    if count > 1:
        return {"error": f"old_text appears {count} times — it must be unique. Refine the selection."}

    updated = original.replace(old_text, new_text, 1)

    try:
        async with await anyio.open_file(path, "w", encoding="utf-8") as f:
            await f.write(updated)
    except OSError as exc:
        return {"error": f"Cannot write file after edit: {exc}"}

    logger.info("file_edit: patched 1 occurrence in %s", path)
    return {"path": path, "status": "ok", "occurrences_replaced": 1}


# ---------------------------------------------------------------------------
# file_delete
# ---------------------------------------------------------------------------


@mcp.tool(tags=_TAG)
async def file_delete(
    path: Annotated[str, Field(description="Absolute path to the file to delete.")],
) -> dict:
    """
    Delete a file from the filesystem.

    Provide the absolute path. Only files are accepted — directory removal is not
    supported. Returns an error if the path does not exist or is a directory.
    """
    if not os.path.exists(path):
        return {"error": f"Path not found: {path}"}
    if os.path.isdir(path):
        return {"error": f"Path is a directory, not a file: {path}. Use shell tooling to remove directories."}

    try:
        os.remove(path)
    except OSError as exc:
        return {"error": f"Cannot delete file: {exc}"}

    logger.info("file_delete: removed %s", path)
    return {"path": path, "status": "deleted"}
