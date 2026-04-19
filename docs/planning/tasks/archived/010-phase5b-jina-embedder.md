# Phase 5b Jina Embedder Tasklist

## Goal

Add a Jina-to-code linking workflow that fetches tickets, embeds ticket text and code, and stores semantic matches in the graph so agents and dashboard views can reason about ticket-to-code relationships.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — Jina embedder can be developed independently; run 007 before integrating Tight FastMCP hooks.

## Dependencies

- Reuse current embedding conventions where possible instead of creating a second incompatible embedding path.
- Keep dashboard integration optional so this task can land before the dashboard starts rendering Jina nodes.
- Follow `docs/planning/design/010-phase5b-jina.md` and the target file map in `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 6
- Planned file edits: 5-6
- Shape: balanced, single task
- Why this size works: the service, tool layer, sample loader, and tests stay under the 15 new-file cap with a moderate edit surface

## Planned Files

New files:
- `src/mem_graph/services/jina_embedder.py`
- `src/mem_graph/tools/integrations/__init__.py`
- `src/mem_graph/tools/integrations/jina.py`
- `scripts/load_jina_sample_data.py`
- `tests/test_jina_embedder.py`
- `tests/test_jina.py`

Existing files to edit:
- `pyproject.toml`
- `src/mem_graph/server.py`
- `src/mem_graph/tools/__init__.py`
- `src/mem_graph/embeddings.py`
- `docs/documentation/configuration.md`
- `docs/documentation/tools.md`

## Tasklist

- [x] Decide whether to wrap the existing embeddings layer or isolate Jina matching behind a service adapter so the repo only has one semantic-search contract.
- [x] Implement a Jina embedder service with lazy model loading, TTL-based unload, and explicit handling for missing Jina credentials.
- [x] Add read-only Jina API fetch support with bounded queries and sane defaults for JQL and result limits.
- [x] Implement code-matching helpers for ticket-to-code and code-to-ticket lookups, including snippet extraction for explainability.
- [x] Add tool endpoints for fetching issues, finding code for a ticket, and finding tickets for a file.
- [x] Persist Jina issue nodes and code-link edges into the graph with stable identifiers.
- [x] Add a sample-data loader or fixture path so the integration can be tested without a live Jina dependency on every run.
- [x] Add tests for lazy loading, TTL unload logic, API result shaping, and semantic match ranking.
- [x] Document required environment variables, expected thresholds, and what “read-only” means for this integration.

## Out Of Scope

- Writing back to Jina
- Webhooks or continuous sync
- Project auto-discovery across multiple Jina instances

## Done When

- [x] Jina issues can be fetched through a tool surface and linked to code files.
- [x] The embedder only loads when needed and can be released after inactivity.
- [x] Graph edges exist for downstream dashboard and agent use.
- [x] The task does not block server startup when Jina is unconfigured.

## References

- `docs/planning/design/010-phase5b-jina.md`
- `docs/planning/design/009-phase5a-dashboard.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
