from __future__ import annotations

import asyncio
import importlib

import pytest

from mem_graph import embeddings as emb


def _reload_embed_modules():
    import mem_graph.services.commands.command_embed as command_embed
    import mem_graph.services.jina.code_embed_service as code_embed_service

    importlib.reload(code_embed_service)
    return importlib.reload(command_embed)


def _rows(result):
    return result if isinstance(result, list) else result.get_all()


def _fake_code_vector(text: str) -> list[float]:
    return [float(len(text) % 5)] * emb.EMBED_DIM


async def _fake_embeddings_code(text: str) -> list[float]:
    await asyncio.sleep(0)
    return _fake_code_vector(text)


@pytest.mark.asyncio
async def test_embed_documents_supports_texts_and_files(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("hello from docs\n", encoding="utf-8")
    command_embed = _reload_embed_modules()

    response = await command_embed.embed_documents(
        texts=["inline text"],
        files=["note.md"],
        root=str(tmp_path),
    )

    assert response["ok"] is True
    assert {item["source"] for item in response["data"]["items"]} == {
        "text:1",
        "note.md",
    }
    assert all(item["dimension"] == emb.EMBED_DIM for item in response["data"]["items"])


@pytest.mark.asyncio
async def test_embed_code_indexes_codefile_nodes(tmp_path, db, monkeypatch):
    source_file = tmp_path / "module.py"
    source_file.write_text("def meaning():\n    return 42\n", encoding="utf-8")
    command_embed = _reload_embed_modules()
    monkeypatch.setattr(command_embed, "embeddings_code", _fake_embeddings_code)

    response = await command_embed.embed_code(root=str(tmp_path), paths=["module.py"])

    assert response["ok"] is True
    assert response["data"]["files_indexed"] == 1

    rows = _rows(
        db.execute(
            "MATCH (f:CodeFile {path: $path}) RETURN count(f)",
            {"path": "module.py"},
        )
    )
    assert rows[0][0] == 1
