# Evals Foundation Tasklist

## Goal

Stand up the core evals framework, baseline suites, scorers, fixtures, and a runnable entry point for audit, fix, and validate agents without exceeding the per-task new-file limit.

Prerequisite: See `docs/planning/tasks/007-fastmcp-task.md` — eval framework is independent; complete 007 before adding any FastMCP-run eval integration.

## Dependencies

- This is the first half of the evals plan. The remaining suite expansion and CI/reporting work is split into `docs/planning/tasks/016-evals-expansion-and-ci.md` to stay under the 15 new-file cap.
- Should align with the agent interfaces that already exist today rather than assuming the future planning wrappers are already in place.
- Follow `docs/planning/design/014-evals.md` and the file targets in `docs/planning/design/FILE_STRUCTURE.md`.

## Work Envelope

- Planned new files: 12
- Planned file edits: 7
- Shape: new-file heavy, capped foundation task
- Why this size works: the framework, core suites, fixtures, and CLI land in one task while leaving map/document expansion for a follow-on task

## Planned Files

New files:
- `src/mem_graph/models/evals.py`
- `src/mem_graph/evals/__init__.py`
- `src/mem_graph/evals/scorers.py`
- `src/mem_graph/evals/evaluator.py`
- `src/mem_graph/evals/audit_evals.py`
- `src/mem_graph/evals/fix_evals.py`
- `src/mem_graph/evals/validate_evals.py`
- `scripts/run_evals.py`
- `tests/test_evals.py`
- `tests/test_scorers.py`
- `tests/fixtures/sample_code.py`
- `tests/fixtures/sample_violations.json`

Existing files to edit:
- `pyproject.toml`
- `pytest.ini`
- `Makefile`
- `README.md`
- `src/mem_graph/agents/audit/audit_agent.py`
- `src/mem_graph/agents/fix/fixer_agent.py`
- `src/mem_graph/agents/validate/validation_agent.py`

## Tasklist

- [ ] Add eval result and suite models that can express stochastic runs, pass rates, durations, and failure detail.
- [ ] Implement scoring helpers for exact match, keyword, regex, and semantic similarity scoring.
- [ ] Build an evaluator runner that can execute a suite multiple times per case and aggregate pass/fail outcomes.
- [ ] Define the first three eval suites for audit, fix, and validate using representative fixture-backed examples.
- [ ] Add a small CLI or script entry point for local eval runs so the framework is usable outside pytest.
- [ ] Add baseline pytest coverage that asserts the framework works and the first suites can run.
- [ ] Update the relevant agent creation points only as needed so eval harnesses can instantiate them cleanly.
- [ ] Document how to run evals locally, what the pass threshold means, and why results are stochastic.

## Out Of Scope

- Map and document eval suites
- Historical report storage in the graph
- CI gates and nightly scheduling

## Done When

- [ ] The repo has a reusable eval framework instead of ad hoc benchmark scripts.
- [ ] Audit, fix, and validate each have at least one maintained eval suite.
- [ ] Developers can run evals from pytest and from a direct script entry point.
- [ ] This task stays at or below the 15 new-file cap by deferring the rest of the suites.

## References

- `docs/planning/design/014-evals.md`
- `docs/planning/design/003-pydantic-deep.md`
- `docs/planning/design/FILE_STRUCTURE.md`
- `docs/planning/design/links.md`
- `https://ai.pydantic.dev/evals/`
