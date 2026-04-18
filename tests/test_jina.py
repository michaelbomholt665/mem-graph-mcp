from __future__ import annotations

import asyncio
import httpx
import pytest


def _fake_vector(text: str) -> list[float]:
    lowered = text.lower()
    vec = [0.0] * 768
    for index, token in enumerate(["auth", "login", "token", "cache", "redis", "billing"]):
        if token in lowered:
            vec[index] = 5.0 - index * 0.4
    return vec


async def _fake_embeddings_code(text: str) -> list[float]:
    await asyncio.sleep(0)
    return _fake_vector(text)


async def _fake_embeddings_code_query(text: str) -> list[float]:
    await asyncio.sleep(0)
    return _fake_vector(text)


@pytest.mark.asyncio
async def test_jina_tools_round_trip(monkeypatch, db, tmp_path):
    from mem_graph.services import jina_embedder as jina_mod
    from mem_graph.services.jina_embedder import JinaCodeEmbedder
    from mem_graph.tools.integrations import jina as jina_tools
    from mem_graph.tools.work.projects import project_create

    monkeypatch.setattr(jina_mod, "embeddings_code", _fake_embeddings_code)
    monkeypatch.setattr(jina_mod, "embeddings_code_query", _fake_embeddings_code_query)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "MEM-88",
                        "fields": {
                            "summary": "Harden login token refresh",
                            "description": {
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "Auth token refresh needs tighter validation."}
                                        ],
                                    }
                                ],
                            },
                            "status": {"name": "Open"},
                            "assignee": {"displayName": "Sam"},
                            "created": "2026-04-10T12:34:56.000+0000",
                        },
                    }
                ]
            },
        )

    service = JinaCodeEmbedder(
        jina_url="https://jina.example.com",
        jina_token="token",
        transport=httpx.MockTransport(handler),
        ttl_seconds=300,
    )
    monkeypatch.setattr(jina_tools, "get_jina_embedder", lambda: service)

    project = await project_create(name="Tools", description="Jina tool tests", repo_path=str(tmp_path))
    project_id = project["project_id"]

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "auth.py").write_text("def validate_login_token():\n    return 'auth login token'\n")
    (src_dir / "cache.py").write_text("def warm_cache():\n    return 'cache redis'\n")

    fetched = await jina_tools.jina_fetch_issues(project_id=project_id)
    assert fetched["count"] == 1
    assert fetched["issues"][0]["key"] == "MEM-88"

    code_matches = await jina_tools.jina_find_code_for_ticket(
        "MEM-88",
        root_path=str(tmp_path),
        project_id=project_id,
        threshold=0.2,
    )
    assert code_matches["count"] == 1
    assert code_matches["matches"][0]["file_path"] == "src/auth.py"

    ticket_matches = await jina_tools.jina_find_tickets_for_file(
        "src/auth.py",
        root_path=str(tmp_path),
        project_id=project_id,
        threshold=0.2,
    )
    assert ticket_matches["count"] == 1
    assert ticket_matches["matches"][0]["key"] == "MEM-88"


@pytest.mark.asyncio
async def test_jina_fetch_issues_reports_config_error(monkeypatch):
    from mem_graph.tools.integrations import jina as jina_tools
    from mem_graph.services.jina_embedder import JinaCodeEmbedder

    monkeypatch.setattr(
        jina_tools,
        "get_jina_embedder",
        lambda: JinaCodeEmbedder(jina_url="", jina_token=""),
    )

    result = await jina_tools.jina_fetch_issues()
    assert "error" in result
    assert "not configured" in result["error"].lower()