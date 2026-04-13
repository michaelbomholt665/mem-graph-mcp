#!/usr/bin/env python3
"""Load sample Jira issues and semantic code links into the graph."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from mem_graph.db import db_close_engine, db_init_engine
from mem_graph.services.jira_embedder import JiraCodeEmbedder, JiraIssue

load_dotenv()

_SAMPLE_ASSIGNEE = "Sample Owner"

SAMPLE_ISSUES = [
    JiraIssue(
        key="MEM-SAMPLE-1",
        title="Harden auth token refresh",
        description="Tighten login token validation and refresh handling.",
        status="Open",
        assignee=_SAMPLE_ASSIGNEE,
        url="https://jira.example.com/browse/MEM-SAMPLE-1",
    ),
    JiraIssue(
        key="MEM-SAMPLE-2",
        title="Reduce cache warmup failures",
        description="Improve Redis cache warmup behavior and observability.",
        status="In Progress",
        assignee=_SAMPLE_ASSIGNEE,
        url="https://jira.example.com/browse/MEM-SAMPLE-2",
    ),
    JiraIssue(
        key="MEM-SAMPLE-3",
        title="Document billing edge cases",
        description="Capture billing validation rules and failure scenarios in code comments or docs.",
        status="Todo",
        assignee=_SAMPLE_ASSIGNEE,
        url="https://jira.example.com/browse/MEM-SAMPLE-3",
    ),
]


async def _load_sample_data(root_path: str, project_id: str | None, limit: int, threshold: float) -> None:
    embedder = JiraCodeEmbedder(
        jira_url=os.getenv("JIRA_URL", "https://jira.example.com"),
        jira_token=os.getenv("JIRA_TOKEN", "sample-token"),
    )
    await embedder.sync_issues(SAMPLE_ISSUES, project_id=project_id)

    for issue in SAMPLE_ISSUES:
        matches = await embedder.find_code_for_issue(
            issue,
            root_path=root_path,
            project_id=project_id,
            limit=limit,
            threshold=threshold,
        )
        print(f"{issue.key}: {len(matches)} match(es)")
        for match in matches:
            print(f"  - {match.file_path} [{match.relation}] score={match.score:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load sample Jira issues and code links into the mem-graph database.")
    parser.add_argument("--root-path", default=str(Path.cwd()), help="Repository root to index for code matches.")
    parser.add_argument("--project-id", default=None, help="Optional Project node ID used to scope issue and file links.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum matches to store per issue.")
    parser.add_argument("--threshold", type=float, default=0.72, help="Semantic match threshold between 0 and 1.")
    args = parser.parse_args()

    db_init_engine()
    try:
        asyncio.run(
            _load_sample_data(
                root_path=args.root_path,
                project_id=args.project_id,
                limit=max(1, args.limit),
                threshold=args.threshold,
            )
        )
    finally:
        db_close_engine()


if __name__ == "__main__":
    main()