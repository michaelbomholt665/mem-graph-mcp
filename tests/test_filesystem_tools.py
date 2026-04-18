#!/usr/bin/env python3
# tests/test_filesystem_tools.py
"""
tests/test_filesystem_tools.py — Unit tests for filesystem tools.

Uses pytest tmp_path fixture for isolated, self-cleaning file operations.
All tests are synchronous (tools are async, run via pytest-asyncio).
"""

from __future__ import annotations

import os

import pytest

from mem_graph.tools.filesystem.filesystem import (
    file_delete,
    file_edit,
    file_grep,
    file_read,
    file_search,
    file_write,
)


# ---------------------------------------------------------------------------
# file_write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_write_creates_file(tmp_path):
    path = str(tmp_path / "test.txt")
    result = await file_write(path, "hello world\n")
    assert result["status"] == "ok"
    assert os.path.isfile(path)
    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "hello world\n"


@pytest.mark.asyncio
async def test_file_write_overwrites(tmp_path):
    path = str(tmp_path / "test.txt")
    await file_write(path, "first\n")
    await file_write(path, "second\n")
    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "second\n"


@pytest.mark.asyncio
async def test_file_write_missing_parent(tmp_path):
    path = str(tmp_path / "nonexistent_dir" / "test.txt")
    result = await file_write(path, "data")
    assert "error" in result


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_read_full(tmp_path):
    path = str(tmp_path / "read.txt")
    content = "line1\nline2\nline3\n"
    await file_write(path, content)
    result = await file_read(path)
    assert result["content"] == content
    assert result["total_lines"] == 3


@pytest.mark.asyncio
async def test_file_read_line_range(tmp_path):
    path = str(tmp_path / "range.txt")
    await file_write(path, "a\nb\nc\nd\n")
    result = await file_read(path, start_line=2, end_line=3)
    assert result["content"] == "b\nc\n"
    assert result["start_line"] == 2
    assert result["end_line"] == 3


@pytest.mark.asyncio
async def test_file_read_missing():
    result = await file_read("/nonexistent/path/to/file.txt")
    assert "error" in result


# ---------------------------------------------------------------------------
# file_search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_search_finds_by_glob(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("x")
    (tmp_path / "c.go").write_text("x")
    result = await file_search(str(tmp_path), "*.py")
    assert result["count"] == 2
    assert all(p.endswith(".py") for p in result["matches"])


@pytest.mark.asyncio
async def test_file_search_missing_dir():
    result = await file_search("/no/such/dir", "*.py")
    assert "error" in result


@pytest.mark.asyncio
async def test_file_search_max_results(tmp_path):
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x")
    result = await file_search(str(tmp_path), "*.txt", max_results=3)
    assert result["count"] == 3
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# file_grep
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_grep_literal(tmp_path):
    path = tmp_path / "code.py"
    path.write_text("def foo():\n    pass\ndef bar():\n    pass\n")
    result = await file_grep(str(tmp_path), "def foo", file_glob="*.py")
    assert result["count"] == 1
    assert result["matches"][0]["line"] == 1


@pytest.mark.asyncio
async def test_file_grep_regex(tmp_path):
    (tmp_path / "code.go").write_text("func Foo() {}\nfunc Bar() {}\n")
    result = await file_grep(str(tmp_path), r"func \w+", file_glob="*.go", is_regex=True)
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_file_grep_invalid_regex(tmp_path):
    result = await file_grep(str(tmp_path), "[invalid", is_regex=True)
    assert "error" in result


# ---------------------------------------------------------------------------
# file_edit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_edit_replaces_once(tmp_path):
    path = str(tmp_path / "edit.py")
    await file_write(path, "def foo():\n    return 1\n")
    result = await file_edit(path, "return 1", "return 42")
    assert result["status"] == "ok"
    assert "return 42" in (tmp_path / "edit.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_file_edit_not_found(tmp_path):
    path = str(tmp_path / "edit.py")
    await file_write(path, "def foo(): pass\n")
    result = await file_edit(path, "DOES_NOT_EXIST", "replacement")
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_file_edit_ambiguous(tmp_path):
    path = str(tmp_path / "edit.py")
    await file_write(path, "x = 1\nx = 1\n")
    result = await file_edit(path, "x = 1", "x = 2")
    assert "error" in result
    assert "appears 2 times" in result["error"]


@pytest.mark.asyncio
async def test_file_edit_missing_file():
    result = await file_edit("/nonexistent/file.py", "old", "new")
    assert "error" in result


# ---------------------------------------------------------------------------
# file_delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_file_delete_removes_file(tmp_path):
    path = str(tmp_path / "del.txt")
    await file_write(path, "x")
    result = await file_delete(path)
    assert result["status"] == "deleted"
    assert not os.path.exists(path)


@pytest.mark.asyncio
async def test_file_delete_missing():
    result = await file_delete("/no/such/file.txt")
    assert "error" in result


@pytest.mark.asyncio
async def test_file_delete_rejects_directory(tmp_path):
    result = await file_delete(str(tmp_path))
    assert "error" in result
    assert "directory" in result["error"]
