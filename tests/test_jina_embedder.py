from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest


def _fake_vector(text: str) -> list[float]:
    lowered = text.lower()
    vec = [0.0] * 768
    weights = {
        0: ("auth", 4.0),
        1: ("login", 3.5),
        2: ("token", 3.0),
        3: ("cache", 4.0),
        4: ("redis", 3.0),
        5: ("billing", 4.0),
    }
    for index, (token, weight) in weights.items():
        if token in lowered:
            vec[index] = weight
    return vec


async def _fake_embeddings_code(text: str) -> list[float]:
    await asyncio.sleep(0)
    return _fake_vector(text)


async def _fake_embeddings_code_query(text: str) -> list[float]:
    await asyncio.sleep(0)
    return _fake_vector(text)


@pytest.mark.asyncio
async def test_fetch_issues_shapes_atlassian_documents(monkeypatch):
    from mem_graph.services.jina.jina_embedder import JinaCodeEmbedder

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/api/3/search"
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "MEM-42",
                        "fields": {
                            "summary": "Improve auth flow",
                            "description": {
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Tighten login token refresh logic.",
                                            }
                                        ],
                                    }
                                ],
                            },
                            "status": {"name": "In Progress"},
                            "assignee": {"displayName": "Ada"},
                            "created": "2026-04-10T12:34:56.000+0000",
                        },
                    }
                ]
            },
        )

    embedder = JinaCodeEmbedder(
        jina_url="https://jina.example.com",
        jina_token="token",
        transport=httpx.MockTransport(handler),
    )

    issues = await embedder.fetch_issues(limit=5)
    assert len(issues) == 1
    assert issues[0].key == "MEM-42"
    assert issues[0].description == "Tighten login token refresh logic."
    assert issues[0].assignee == "Ada"
    assert issues[0].url == "https://jina.example.com/browse/MEM-42"
    assert issues[0].created_at is not None


@pytest.mark.asyncio
async def test_find_code_for_issue_ranks_matches_and_unloads(monkeypatch, db, tmp_path):
    from mem_graph.services.jina import jina_embedder as jina_mod
    from mem_graph.services.jina.jina_embedder import JinaCodeEmbedder, JinaIssue
    from mem_graph.tools.work.projects import project_create

    monkeypatch.setattr(jina_mod, "embeddings_code", _fake_embeddings_code)
    monkeypatch.setattr(jina_mod, "embeddings_code_query", _fake_embeddings_code_query)

    project = await project_create(
        name="Atlas", description="Jina linking test", repo_path=str(tmp_path)
    )
    project_id = project["project_id"]

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "auth.py").write_text(
        "def refresh_auth_token():\n    return 'login token auth'\n"
    )
    (src_dir / "cache.py").write_text("def warm_cache():\n    return 'cache redis'\n")

    embedder = JinaCodeEmbedder(
        jina_url="https://jina.example.com", jina_token="token", ttl_seconds=60
    )
    issue = JinaIssue(
        key="MEM-7",
        title="Improve auth login token handling",
        description="Auth token refresh should be safer.",
        status="Open",
        url="https://jina.example.com/browse/MEM-7",
    )

    matches = await embedder.find_code_for_issue(
        issue,
        root_path=str(tmp_path),
        project_id=project_id,
        threshold=0.2,
        limit=2,
    )

    assert [match.file_path for match in matches] == ["src/auth.py"]
    assert matches[0].relation == "IMPLEMENTS"
    assert embedder.index_loaded is True
    assert embedder.indexed_file_count == 2

    jina_rows = db.execute(
        "MATCH (j:JinaIssue {id: $id}) RETURN j.issue_key", {"id": issue.issue_id()}
    )
    assert jina_rows.get_all()[0][0] == "MEM-7"

    link_rows = db.execute(
        """
        MATCH (j:JinaIssue {id: $issue_id})-[:IMPLEMENTS]->(f:CodeFile)
        RETURN f.path
        """,
        {"issue_id": issue.issue_id()},
    )
    assert link_rows.get_all()[0][0] == "src/auth.py"

    released = embedder.release_idle_resources(
        now=datetime.now(timezone.utc) + timedelta(seconds=61)
    )
    assert released is True
    assert not embedder.index_loaded
