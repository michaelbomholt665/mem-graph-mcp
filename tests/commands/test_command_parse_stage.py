from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _reload_parse_stage():
    import mem_graph.services.commands.command_parse_stage as command_parse_stage

    return importlib.reload(command_parse_stage)


def _rows(result):
    return result if isinstance(result, list) else result.get_all()


@pytest.mark.asyncio
async def test_code_stage_and_commit_index_round_trip(tmp_path, db):
    source_file = tmp_path / "sample.py"
    source_file.write_text(
        "def add(left, right):\n    return left + right\n", encoding="utf-8"
    )
    command_parse_stage = _reload_parse_stage()

    staged = command_parse_stage.code_stage(root=str(tmp_path), path="sample.py")
    committed = command_parse_stage.code_commit_index(root=str(tmp_path))

    assert staged["staged_count"] == 1
    assert Path(staged["staged"][0]["stage_path"]).exists() is False
    assert committed["committed"] == ["sample.py"]

    rows = _rows(
        db.execute(
            "MATCH (f:CodeFile {path: $path}) RETURN count(f)",
            {"path": "sample.py"},
        )
    )
    assert rows[0][0] == 1


@pytest.mark.asyncio
async def test_code_parse_returns_file_summary(tmp_path):
    source_file = tmp_path / "parse_me.py"
    source_file.write_text(
        "def square(value):\n    return value * value\n", encoding="utf-8"
    )
    command_parse_stage = _reload_parse_stage()

    response = command_parse_stage.code_parse(root=str(tmp_path), path="parse_me.py")

    assert response["mode"] == "file"
    assert response["file"]["relative_path"] == "parse_me.py"
    assert response["file"]["has_batch"] is True
