# Task 036: Evaluation Infrastructure — Comprehensive AI Agent Testing

**Status:** Planning
**Priority:** High
**Blocked by:** Tasks 029–035 (all prior tasks)
**Blocks:** None (final in sequence)
**Complexity:** LARGE

## Problem Statement

The current eval infrastructure has only 5 suites covering core agents (audit, document, fix, map, validate). Missing entirely: router, sentry, orchestrator, triage, chat, rule_injector agents, and all 29 planned workflows. No skill-level evals measure individual domain-knowledge bundle performance. Eval infrastructure is incomplete: no timeout on live runners, sequential suite execution, missing Unicode normalization in text scoring.

The goal is to:
1. **Create comprehensive agent evals** — one per agent, measuring key behavioral claims.
2. **Establish workflow evals** — end-to-end testing of orchestration patterns.
3. **Add skill evals** — independent measurement of domain-knowledge quality.
4. **Fix infrastructure issues** — parallelization, timeout enforcement, text normalization.
5. **Enable GEPA loop** — eval results feed back into prompt optimization.

## Goals

1. **Add missing agent evals** — router, sentry, orchestrator, triage, chat, rule_injector (6 suites).
2. **Add workflow evals** — autopilot, package_audit, feature_implementation (3 suites).
3. **Add skill evals** — python_quality, security, go_quality, typescript_quality (4 suites).
4. **Fix eval infrastructure** — parallelization, timeouts, Unicode, regex pre-compilation.
5. **Add span-based evals** — OTel spans for reasoning path validation.
6. **Document eval patterns** — guide for adding new evals.

## Non-Goals

- Building a web UI for eval visualization (future enhancement).
- Implementing GEPA itself (that's Task 026).
- Changing Pydantic AI validation mechanism.

## Current State

### Existing Eval Suites (5)

| Suite | Agent(s) | Fixture Cases | Live Cases | Status |
|-------|----------|---------------|-----------|--------|
| `audit` | `audit_agent` | 10+ | 10+ | Complete |
| `document` | `decision_agent`, `task_agent`, `scribe_agent` | 15+ | 15+ | Complete |
| `fix` | `fixer_agent` | 10+ | 10+ | Complete |
| `map` | `map_agent` | 8+ | 8+ | Complete |
| `validate` | `validation_agent` | 5+ | 5+ | Complete |

### Missing Evals (14)

**Agent-level (6):**
- `router_evals` — 5 claims (Routes to correct tier, mode selection, task decomposition)
- `sentry_evals` — 3 claims (Failing test proposals, framework detection, scope violation check)
- `orchestrator_evals` — 4 claims (Sub-agent dispatch, report generation, retry handling, partial failure)
- `triage_evals` — 2 claims (Deduplication, severity promotion)
- `chat_evals` — 2 claims (Graph grounding, no code changes)
- `rule_injector_evals` — 2 claims (Rule selection for language, exclusion logic)

**Workflow-level (3):**
- `workflow_autopilot_evals` — 4 claims (Guard approval, rejection, memory sync, success flag)
- `workflow_package_audit_evals` — 3 claims (File count accuracy, deduplication, critical finding detection)
- `workflow_feature_implementation_evals` — 2 claims (Sentry before fixer, fixer scope)

**Skill-level (4):**
- `skill_python_quality_evals` — Precision/recall on Python code
- `skill_security_evals` — Precision/recall on security patterns
- `skill_go_quality_evals` — Precision/recall on Go idioms
- `skill_typescript_quality_evals` — Precision/recall on TS patterns

### Infrastructure Issues

| Severity | Issue | Fix |
|----------|-------|-----|
| Medium | No timeout on live runner | `asyncio.wait_for` with configurable timeout |
| Medium | Sequential suite execution | Parallelise cases within suite using `anyio.create_task_group` |
| Low | Missing key in `_FIXTURE_OUTPUTS` raises KeyError | Safe `.get()` with descriptive error |
| Low | Regex in scorers allows arbitrary patterns | Pre-compile and validate at suite load time |
| Low | `fixtures._repo_root` uses fragile `parents[3]` | Use `importlib.resources` or env var |
| Info | `persist_report_summary(conn: Any)` loses typing | Type as `lb.Connection` or Protocol |
| Info | `_normalize_text` has no Unicode normalization | `unicodedata.normalize("NFKD", value)` |

## Target Files

### New Files

```
evals/suites/router_evals.py
  - Router agent behavioral claims (tier selection, mode, task decomposition)

evals/suites/sentry_evals.py
  - Sentry agent behavioral claims (test proposals, framework detection)

evals/suites/orchestrator_evals.py
  - Orchestrator agent behavioral claims (sub-agent dispatch, reports, retries)

evals/suites/triage_evals.py
  - Triage agent behavioral claims (deduplication, severity)

evals/suites/chat_evals.py
  - Chat agent behavioral claims (graph grounding, scope)

evals/suites/rule_injector_evals.py
  - Rule injector agent behavioral claims (rule selection, exclusion)

evals/suites/workflow_autopilot_evals.py
  - Autopilot graph end-to-end claims

evals/suites/workflow_package_audit_evals.py
  - Package audit graph end-to-end claims

evals/suites/workflow_feature_implementation_evals.py
  - Feature implementation workflow claims (planned; waits on workflow implementation)

evals/suites/skill_evals.py
  - Skill precision/recall suites (python_quality, security, go_quality, typescript_quality)

docs/planning/design/evals/eval-authoring-guide.md
  - Template for adding new evals
  - Checklist for claim validation
```

### Modifications

```
evals/evaluator.py
  - Add timeout enforcement for all runners
  - Add parallelization within suites
  - Improve error messages

evals/scorers.py
  - Add Unicode normalization to _normalize_text
  - Pre-compile and validate regex patterns at suite load
  - Add type hints for all scorers

evals/fixtures.py
  - Use importlib.resources for repo root detection
  - Add safety checks for missing fixture keys

evals/__init__.py
  - Export all eval suites and evaluators
```

## Implementation Phases

### Phase 1: Infrastructure Fixes (Sprint 1)

**Fix `evaluator.py`:**
- [ ] Add timeout enforcement:
  ```python
  async def run_case(self, suite, case, runner, ...) -> EvalCaseResult:
      try:
          result = await asyncio.wait_for(
              runner(case),
              timeout=case.timeout_s or self.DEFAULT_CASE_TIMEOUT_S,
          )
          return EvalCaseResult(passed=True, ...)
      except asyncio.TimeoutError:
          return EvalCaseResult(passed=False, reason="timeout", ...)
  ```

- [ ] Add parallelization:
  ```python
  async def run_suite(self, binding, ...) -> EvalSuiteResult:
      cases = binding.cases
      results = []

      async with anyio.create_task_group() as tg:
          for case in cases:
              results.append(
                  tg.start_soon(self.run_case, binding, case, runner)
              )

      return EvalSuiteResult(case_results=results, ...)
  ```

**Fix `scorers.py`:**
- [ ] Add Unicode normalization:
  ```python
  def _normalize_text(value: str) -> str:
      """Normalize text for comparison."""
      import unicodedata
      # NFKD: compatibility decomposition (é → e + combining accent)
      value = unicodedata.normalize("NFKD", value)
      # Remove accents
      value = "".join(c for c in value if unicodedata.category(c) != "Mn")
      return value.lower()
  ```

- [ ] Pre-compile regex:
  ```python
  def regex_score(output: str, pattern: str) -> float:
      """Score based on regex match."""
      try:
          regex = re.compile(pattern)  # Validate on first call
      except re.error as e:
          raise ValueError(f"Invalid regex: {pattern}") from e

      return 1.0 if regex.search(output) else 0.0
  ```

**Fix `fixtures.py`:**
- [ ] Use importlib.resources:
  ```python
  from importlib.resources import files

  def get_repo_root() -> Path:
      """Get repo root using importlib.resources."""
      # Rather than fragile parents[3] heuristic
      return Path(files("mem_graph")).parent.parent.parent
  ```

### Phase 2: Add Missing Agent Evals (Sprint 1–2)

**Create `evals/suites/router_evals.py`:**
- [ ] Define router claims:
  ```python
  ROUTER_CASES = [
      EvalCase(
          name="route_violation_fix_to_standard_tier",
          prompt="Fix this SQL injection vulnerability in line 42",
          expected_output={"tier": "STANDARD"},
          claim="Routes fix task to STANDARD tier, not AUTOPILOT",
      ),
      EvalCase(
          name="route_codebase_audit_to_orchestrator",
          prompt="Audit the entire codebase for security issues",
          expected_output={"solo_mode": False},
          claim="Routes full audit to orchestrator (not solo agent)",
      ),
      EvalCase(
          name="decompose_into_subtasks",
          prompt="Refactor the payment module: modernize typing, add tests, fix bugs",
          expected_output={"sub_tasks": [...]},
          claim="Decomposes multi-part request into subtasks",
      ),
      EvalCase(
          name="no_workflow_plan_in_route_only_mode",
          prompt="Should I refactor this code?",
          dependencies={"workflow_mode": "route_only"},
          expected_output={"workflow_plan": None},
          claim="Does not produce workflow_plan in route_only mode",
      ),
      EvalCase(
          name="select_subagent_workflow_when_requested",
          prompt="Design this feature with full workflow planning",
          dependencies={"request_workflow": True},
          expected_output={"workflow_mode": "subagent_workflow"},
          claim="Selects subagent_workflow mode when explicitly requested",
      ),
  ]
  ```

**Create `evals/suites/sentry_evals.py`:**
- [ ] Define sentry claims (test proposals, framework detection, scope).

**Create `evals/suites/orchestrator_evals.py`:**
- [ ] Define orchestrator claims (sub-agent dispatch, reports, retries, partial failure).

**Similar for `triage_evals.py`, `chat_evals.py`, `rule_injector_evals.py`.**

### Phase 3: Add Workflow Evals (Sprint 2)

**Create `evals/suites/workflow_autopilot_evals.py`:**
- [ ] End-to-end autopilot claims:
  ```python
  AUTOPILOT_CASES = [
      WorkflowEvalCase(
          name="guard_approves_clean_patch",
          target_codebase="clean_python_code",  # No violations
          patch="Add type hints to function signature",
          expected={"approval": True, "retry_count": 0},
          claim="GuardNode approves patch with zero retries",
      ),
      WorkflowEvalCase(
          name="guard_rejects_introducing_violation",
          target_codebase="clean_python_code",
          patch="Add unparameterised SQL query",
          expected={"approval": False},
          claim="GuardNode rejects patch that introduces new violation",
      ),
      WorkflowEvalCase(
          name="memory_sync_writes_summary",
          target_codebase="python_with_violations",
          expected={"summary_written": True, "summary_word_count": ">50"},
          claim="MemorySyncNode writes summary note to graph",
      ),
      WorkflowEvalCase(
          name="success_flag_when_all_files_pass",
          target_codebase="python_with_violations",
          expected={"success": True},
          claim="AutopilotState.success = True when all files pass guard",
      ),
  ]
  ```

**Create `evals/suites/workflow_package_audit_evals.py`:**
- [ ] Package audit claims (file count, deduplication, critical findings).

### Phase 4: Add Skill Evals (Sprint 2–3)

**Create `evals/suites/skill_evals.py`:**
- [ ] Skill precision/recall:
  ```python
  PYTHON_QUALITY_SKILL_CASES = [
      SkillEvalCase(
          skill_name="python_quality",
          code_snippet="x = map(int, ['1', '2'])",
          expected_violations=["PY001"],  # Comprehension rule
          claim="Detects non-comprehension map usage (recall)",
      ),
      SkillEvalCase(
          skill_name="python_quality",
          code_snippet="x = [int(s) for s in ['1', '2']]",
          expected_violations=[],
          claim="Does not flag idiomatic list comprehension (precision)",
      ),
      # ... more cases
  ]

  SECURITY_SKILL_CASES = [
      SkillEvalCase(
          skill_name="security",
          code_snippet='query = f"SELECT * FROM users WHERE id = {uid}"',
          expected_violations=["SEC-SQL"],
          claim="Detects SQL injection vector",
      ),
      SkillEvalCase(
          skill_name="security",
          code_snippet='query = "SELECT * FROM users WHERE id = ?" ; cursor.execute(query, (uid,))',
          expected_violations=[],
          claim="Accepts parameterised SQL (no false positive)",
      ),
  ]
  ```

### Phase 5: Add Span-Based Evals (Sprint 3)

**Extend evaluator to use OTel spans:**
- [ ] Span tree validation:
  ```python
  from pydantic_evals.evaluators import HasMatchingSpan

  class SpanEvalCase:
      """Eval case checking for specific span patterns."""
      span_query: dict  # {"name": "audit", "attributes": {"file_count": ">0"}}
      claim: str

  ORCHESTRATOR_SPAN_CASES = [
      SpanEvalCase(
          span_query={"name": "sentry", "children": {"name": "test_plan_count", ">": 0}},
          claim="Sentry span exists and produced test plans",
      ),
      SpanEvalCase(
          span_query={"name": "guard", "attributes": {"retry_count": "<", "max_retries"}},
          claim="Guard retry count < max_retries",
      ),
  ]
  ```

### Phase 6: Documentation (Sprint 3)

- [ ] Create `docs/planning/design/evals/eval-authoring-guide.md`:
  ```markdown
  # Eval Authoring Guide

  ## Anatomy of an Eval Suite

  One eval suite per agent or workflow. Each suite contains fixture cases (CI-gated, fast) and live cases (release-gated, costly).

  ```python
  # evals/suites/my_agent_evals.py

  MY_AGENT_FIXTURE_CASES = [
      EvalCase(
          name="claim_1",  # Unique name
          prompt="...",    # Input to agent
          expected_output={...},  # Expected structure
          claim="...",     # One-sentence behavioral claim
          rationale="...", # Why this claim matters
      ),
      # More cases
  ]

  MY_AGENT_LIVE_CASES = [
      # More challenging cases; run only in release gate
  ]

  SUITE_BINDING = EvalSuiteBinding(
      agent=my_agent,
      fixture_cases=MY_AGENT_FIXTURE_CASES,
      live_cases=MY_AGENT_LIVE_CASES,
      default_runs=3,  # How many times to run each case
      pass_threshold=0.67,  # 2/3 must pass
  )
  ```

  ## Testing Checklist

  - [ ] Each case has exactly one claim
  - [ ] Cases cover happy path + edge cases
  - [ ] Expected output type matches agent output_type
  - [ ] Claims are falsifiable (not vacuous)
  - [ ] Fixture cases run in <5s total
  - [ ] Live cases have reasonable timeouts
  ```

## Acceptance Criteria

1. **6 new agent evals created:** router, sentry, orchestrator, triage, chat, rule_injector.
2. **3 workflow evals created:** autopilot, package_audit, feature_implementation.
3. **4 skill evals created:** python_quality, security, go_quality, typescript_quality.
4. **Infrastructure fixed:** Timeouts enforced, parallelization, Unicode normalization, regex validation.
5. **Span-based evals enabled:** OTel span validation for reasoning paths.
6. **Fixture cases 90%+ pass:** All fixture evals pass at ≥90% rate.
7. **Live cases tracked:** Live evals baseline established for release gate.
8. **Documentation complete:** Authoring guide enables new eval creation.

## Test Plan

```bash
# Run all fixture evals (CI gate)
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals --mode fixture

# Run agent evals only
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals router sentry orchestrator triage chat rule_injector --mode fixture

# Run workflow evals only
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals workflow_autopilot workflow_package_audit --mode fixture

# Run skill evals only
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals skill_python_quality skill_security --mode fixture

# Test infrastructure fixes
uv run pytest evals/test_evaluator_fixes.py -q

# Run live evals (release gate)
uv run mem-graph-evals --mode live --push

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run mem-graph-evals
```

## Dependencies

- Tasks 029–035 (all prior infrastructure tasks).
- Pydantic Evals framework (no changes needed).
- Logfire for span tree capture (optional, but enables span-based evals).

## Notes

- Fixture pass rate of 90%+ is baseline; live evals will have lower rates (60–75%) due to stochasticity.
- Eval results feed into GEPA loop (Task 026) for autonomous prompt optimization.
- Skill evals enable per-domain performance tracking — useful for deciding which skills to activate.
- Workflow evals should run longer (~500 tokens cost per end-to-end case) — good for release validation but expensive for CI.
