# Evals Expansion And CI Tasklist

## Goal

Finish the remaining eval coverage, add persistence and reporting hooks, and wire the eval framework into repeatable CI and release checks after the foundation task lands.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — expansion is independent, but finalize 007 before adding FastMCP-specific eval runners.

## Dependencies

- Requires `docs/planning/tasks/014-evals-foundation.md` to be complete first.
- Should build on real eval output and fixtures rather than introducing a second parallel benchmark format.
- Follows the second half of `docs/planning/design/014-evals.md`.

## Work Envelope

- Planned new files: 7
- Planned file edits: 7-8
- Shape: balanced follow-on task
- Why this size works: keeps the remaining suite growth, graph persistence, and CI wiring separate from the framework bootstrap task

## Planned Files

New files:
- `src/mem_graph/evals/map_evals.py`
- `src/mem_graph/evals/document_evals.py`
- `tests/test_map_evals.py`
- `tests/test_document_evals.py`
- `tests/test_fix_evals.py`
- `tests/test_validate_evals.py`
- `tests/fixtures/sample_graph_data.json`

Existing files to edit:
- `src/mem_graph/evals/evaluator.py`
- `src/mem_graph/server.py`
- `src/mem_graph/db.py`
- `tests/test_evals.py`
- `Makefile`
- `README.md`
- `docs/documentation/testing.md`
- `docs/documentation/api.md`

## Tasklist

- [x] Add the remaining suite definitions for map and document behaviors, plus any additional coverage needed for fix and validate regressions.
- [x] Extend the evaluator so it can emit machine-readable reports and optionally persist summary results to the graph.
- [x] Add fixture coverage for graph-shaped data and multi-agent outputs that the foundation task intentionally skipped.
- [x] Expand pytest coverage to include suite-specific tests and tier comparison assertions where they are stable enough to be useful.
- [x] Add repeatable Makefile and documentation entry points for local, CI, and release-time eval runs.
- [x] Define how eval failures should gate merges or releases without making local development unusably slow.
- [x] Document maintenance rules for updating suites when prompts, tools, or agent contracts change.

## Out Of Scope

- Automatic prompt tuning based on eval results
- Production-time eval execution
- Large-scale distributed eval runners

## Done When

- [x] Map and document agent behaviors are covered by maintained eval suites.
- [x] Evals can be run consistently in local and CI contexts.
- [x] The repo has a clear story for storing or reporting eval outcomes over time.
- [x] The split between foundation and expansion keeps both tasks below the requested file-count limit.

## References

- `docs/planning/design/014-evals.md`
- `docs/planning/tasks/014-evals-foundation.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `https://ai.pydantic.dev/evals/`
