# 08 — Evals

## Principle

AI agents are probabilistic. A unit test that passes 100% of the time may still fail 30% of the time in production. Evals run agents against realistic inputs multiple times, measure output quality, and track pass-rate over time. They are the correctness signal equivalent to type-checking — a permanently maintained suite, not a one-off check.

> **Direction:** Many small, tightly-scoped evals — one per claim about an agent's behaviour — are preferable to a few large evals that bundle multiple concerns. Large evals are hard to diagnose when they regress. Small evals give you a diff: "this specific claim stopped being true after this change."

---

## Current Eval Infrastructure

### Evaluator (`evals/evaluator.py`)

```python
class Evaluator:
    async def run_case(suite, case, runner, ...) -> EvalCaseResult
    async def run_suite(binding, ...) -> EvalSuiteResult
    async def run_report(registry, ...) -> EvalReport
    def persist_report_summary(report, *, conn, project_id, ...) -> str
```

Each case runs `N` times and measures pass-rate:
- `DEFAULT_PASS_THRESHOLD = 0.67` — allows one miss in three runs (stochastic tolerance)
- `DEFAULT_RUNS = 3` — minimum for meaningful variance measurement
- `DEFAULT_CASE_TIMEOUT_S = 120` — per-case timeout

`persist_report_summary()` writes an `EvalRun` node to the Ladybug graph, linked to the target project via `HAS_EVAL_RUN`.

### Scoring (`evals/scorers.py`)

| Scorer | Type | Best for |
|--------|------|---------|
| `exact` | Deterministic | Enum fields, status codes |
| `keywords` | Deterministic | Presence of required terms in output |
| `regex` | Deterministic | Structured format validation |
| `semantic` | Embedding-based | Meaning-preserving paraphrase (degrades to token overlap without `sentence_transformers`) |
| `HostedTextScorer` | LLM-as-a-judge | Open-ended reasoning, explanation quality |

**Known issue:** `_normalize_text` does not apply Unicode normalisation — accent-bearing terms or curly quotes from an LLM response will silently under-count keyword matches. Fix: `unicodedata.normalize("NFKD", value)`.

### Eval Modes

| Mode | Source | Use case |
|------|--------|---------|
| `fixture` | Local `fixtures.py` deterministic inputs | CI gate, regression testing, offline |
| `live` | Logfire hosted datasets | Release confidence, model upgrade validation |

```bash
# CI gate (no network, no model credits needed)
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run mem-graph-evals --mode fixture
make evals-ci

# Live (requires Logfire + model credentials)
uv run mem-graph-evals --mode live
```

---

## Current Eval Suites (5 — insufficient)

| Suite | Agent(s) under test | Cases |
|-------|--------------------|----|
| `audit` | `audit_agent` | fixture + live |
| `document` | `decision_agent`, `task_agent`, `scribe_agent` | fixture + live |
| `fix` | `fixer_agent` | fixture + live |
| `map` | `map_agent` | fixture + live |
| `validate` | `validation_agent` | fixture + live |

Missing entirely: `router_agent`, `sentry_agent`, `orchestrator_agent`, `chat_agent`, `triage_agent`, all 29 planned workflow resources, and the `rule_injector_agent`.

---

## Target Eval Catalogue

### Agent-Level Evals (one claim per case)

**`router_evals`** — `router_agent`:
- Routes `"fix this violation"` to `ModelTier.STANDARD`, not `AUTOPILOT`
- Routes `"audit the whole codebase"` to `orchestrator_run`, not single-file audit
- Produces at least one `sub_task` for multi-file requests
- Does not produce a `workflow_plan` in `route_only` mode
- Selects `subagent_workflow` mode when explicitly requested

**`sentry_evals`** — `sentry_agent`:
- Produces at least one failing test proposal for a known violation
- Identifies the correct test framework from a `pyproject.toml` manifest
- Does not propose production code changes (scope violation)

**`orchestrator_evals`** — `orchestrator_agent`:
- Dispatches the correct sub-agent for each `subagent_name`
- Produces a non-empty `OrchestratorReport` for a 3-file batch
- Terminates within `max_retries` even when all files fail to read
- `partial_failure` is `True` when any file in the batch errors

**`triage_evals`** — `triage_agent`:
- Correctly deduplicates two violations with identical `rule + file_path`
- Promotes severity from `medium` to `high` when blast-radius is wide

**`chat_evals`** — `chat_agent`:
- Grounds answer in retrieved graph node IDs (cites at least one)
- Does not propose code changes in response to a read-only query

**`rule_injector_evals`** — `rule_injector_agent`:
- Selects security rules for a file containing HTTP request handling
- Excludes documentation rules for a non-Python file

---

### Workflow-Level Evals

**`workflow_autopilot_evals`** — autopilot graph end-to-end:
- `GuardNode` approves a clean patch in ≤ 1 retry
- `GuardNode` rejects a patch that introduces a new violation
- `MemorySyncNode` writes exactly one summary note to the graph per run
- `AutopilotState.success = True` when all files pass guard

**`workflow_package_audit_evals`** — `run_package_audit`:
- `PackageAuditReport.total_files` equals the file count discovered
- Deduplication removes duplicate findings with identical `(file, rule, description[:100])`
- `critical_findings` list is non-empty for a snippet with a known critical violation

**`workflow_feature_implementation_evals`** (planned):
- Sentry writes at least one failing test before fixer runs
- Fixer patches touch only files listed in `target_files`

---

### Skill-Level Evals (future — once `resources/skills/` exists)

Each `SkillBundle` gets its own eval suite measuring precision + recall of audit findings:

**`skill_python_quality_evals`**:
- Known violation snippet → auditor finds it (recall)
- Clean snippet → auditor finds nothing (precision)

**`skill_security_evals`**:
- Snippet with SQL injection → auditor flags it
- Snippet with parameterised query → auditor clears it

---

### Scorer-Level Evals

The scoring functions themselves need reliability tests:

- `exact_score`: `"approved"` ≠ `"APPROVED"` → score 0.0
- `keyword_score`: `"drift"` present in output that contains `"drifted"` → score ≥ 0.5
- `semantic_score`: paraphrase of expected output → score > 0.7
- Unicode: `"résumé"` matches `"resume"` after normalisation

---

### Span-Based Evals (Logfire integration — API validated)

Evaluate **reasoning paths**, not just final output. The `EvaluatorContext.span_tree` attribute
provides a graph of OpenTelemetry spans recorded during the agent's execution.

**Target reasoning paths:**

```
orchestrator.run
  └── sentry         → span: test_plan_count > 0
  └── logic_draft    → span: patch_count > 0
  └── guard          → span: retry_count < max_retries
  └── memory_sync    → span: success = True
```

**Quick option — built-in `HasMatchingSpan`:**

```python
from pydantic_evals.evaluators import HasMatchingSpan

# Check that the security scan tool ran before patch approval
has_scan = HasMatchingSpan(query={"name": "sql_injection_scan"})
```

**Custom evaluator pattern:**

```python
from pydantic_evals import Evaluator, EvaluatorContext, EvaluationReason

class RetryCountCheck(Evaluator[AutopilotInput, AutopilotOutput, None]):
    """Guard did not exceed max_retries."""

    async def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        guard_span = next(
            (s for s in ctx.span_tree if s.name == "guard"), None
        )
        if guard_span is None:
            return EvaluationReason(result=False, reason="guard span not found")
        retry_count = guard_span.attributes.get("retry_count", 0)
        max_retries = guard_span.attributes.get("max_retries", 3)
        return EvaluationReason(
            result=retry_count < max_retries,
            reason=f"retries={retry_count}, max={max_retries}",
        )
```

**Configuration requirements:**
- Logfire or OTel backend must be active during the task run for `span_tree` to populate.
- `EvaluatorContext` captures `trace_id` and `span_id` automatically.
- `HasMatchingSpan` is preferred for simple presence checks; custom `Evaluator` subclasses
  for attribute assertions or multi-span logic.

---

## Known Infrastructure Issues (from `009-evals-package.md`)

| Severity | Issue | Fix |
|----------|-------|-----|
| Medium | No timeout on live runner — evals can hang indefinitely | `asyncio.wait_for` already applied; extend to live runners |
| Medium | Fully sequential suite execution | Parallelise cases within a suite using `anyio.create_task_group` |
| Low | Missing key in `_FIXTURE_OUTPUTS` raises unguarded `KeyError` | Safe `.get()` with a descriptive error |
| Low | `scorers.regex_score` allows arbitrary user regex — potential ReDoS | Pre-compile and validate regex patterns at suite load time |
| Low | `fixtures._repo_root` uses fragile `parents[3]` | Use `importlib.resources` or an env-var anchor |
| Info | `persist_report_summary(conn: Any)` loses static typing | Type as `lb.Connection` or a Protocol |
| Info | `_normalize_text` has no Unicode normalisation | `unicodedata.normalize("NFKD", value)` |

---

## GEPA: Self-Improving Evaluation Loop

GEPA (Genetic-Pareto Prompt Evolution) creates a reflective loop where eval results serve as
structured feedback for the optimisation agent. See `00-2-GEPA.md` for the full pattern.

Key integration points with the eval infrastructure:

| GEPA Step | Eval Mechanism | Notes |
|-----------|---------------|-------|
| Evaluate candidates | `Evaluator.run_suite()` / `run_report()` | Runs N times, tracks pass-rate |
| Capture trajectories | `EvaluatorContext.span_tree` | OTel spans from Logfire |
| Build reflective dataset | `persist_report_summary()` → `EvalRun` node | Written to Ladybug graph |
| Propose mutations | Proposer LLM + `Agent.override()` | Inject candidate prompt thread-safely |
| Pareto selection | Accept/reject gate in proposer output | Only improvements land |

The **Agent Builder** (`agents/builder/agent_builder.py`) is the component responsible for
consuming eval failure data and updating agent/skill specs. Its `agent_builder_update` prompt
is the current entry point for evidence-based spec refinement.

---

## Command Catalog Integration (`eval gate`, `eval test`)

The CLI Command Catalog (Task 027) provides concrete entry points for the eval infrastructure:

| CLI Command | Maps to | Notes |
|-------------|---------|-------|
| `eval gate` | Fixture, CI, live, and release eval gates | Span-based validation via `span_tree` |
| `eval test` | `sentry_agent` — failing test proposals | Runs at `ModelTier.MICRO` inside `SentryNode` |

`eval gate` executes:
```bash
# CI gate (no network, no model credits needed)
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true uv run mem-graph-evals --mode fixture
make evals-ci

# Release gate (requires Logfire + model credentials)
uv run mem-graph-evals --mode live --push
```

The `eval gate` command is wired through `services/command_evals.py` (see Task 027, Phase 3).

---

## Eval CLI Reference

```bash
uv run mem-graph-evals                              # all fixture suites
uv run mem-graph-evals audit fix                   # selected suites
uv run mem-graph-evals --runs 5                    # override run count
uv run mem-graph-evals --output build/report.json  # JSON report
uv run mem-graph-evals --push                      # push golden sets to Logfire
uv run mem-graph-evals --hosted                    # run against Logfire datasets
uv run mem-graph-evals --persist-project-id proj_123 --persist-trigger ci
```
