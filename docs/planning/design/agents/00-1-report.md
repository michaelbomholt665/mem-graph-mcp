# 00-1 — Technical Mapping Report: CLI Command Catalog to Agent Architecture

> **Status:** Reference document (research synthesis)
> **Source:** Session `6e0f4bf2` gap-fill research + `027-commands.md` integration analysis
> **See also:** `00-2-GEPA.md` (GEPA pattern), `00-researcha-acomments.md` (raw research notes)

---

## Overview

This document maps the curated CLI Command Catalog (`docs/planning/tasks/027-commands.md`) to the
agent and workflow architecture documented in `01–08-*.md`. It provides the concrete binding between
abstract agent personas and executable development lifecycle operations.

---

## 1. Architectural Foundation

### 1.1 Stateless Agent Execution Model

Base agents are globally-instantiated service objects — conceptually identical to FastAPI router
instances. They do not maintain runtime state; all mutable context flows through typed `@dataclass`
dependencies (`deps_type`) injected per-run via `RunContext`.

**Key design principles:**

- **Skills as Context:** Every agent's `deps_type` includes a `skills_content: str` field — the
  stable interface for injecting `SkillBundle` prompt fragments at call-time.
- **Cache-optimised prompts:** All task-specific context is pushed to `@agent.system_prompt`,
  re-evaluated per run. The framework sorts prompts to maximise provider-side prompt-cache hit
  rates, preventing monolithic master prompts from wasting prefill tokens.

### 1.2 Tool Curation Strategy (Tiers 1–3)

| Tier | Name | Description | Access |
|------|------|-------------|--------|
| **Tier 1** | Visible | High-level orchestrator tools (`memory_recall`, `confirm_action`) | 5–8 max; always loaded |
| **Tier 2** | Searchable | Domain-specific tools (`audit_package`, `task_decompose_feature`) | Namespace-activated |
| **Tier 3** | Invisible | Granular primitives (`file_read`, `graph_traverse`, `parse_file`) | Agent-local or workflow nodes only |

**Tier 3 restriction logic:** Granular primitives are restricted to prevent "primitive leaking."
This forces the LLM to use service-backed, outcome-oriented Tier 2 tools rather than manually
orchestrating low-level storage or I/O — which is brittle and token-expensive.

### 1.3 Workflow Orchestration

Workflows are managed via `pydantic-graph` as a Python-owned finite state machine (FSM). Python
retains absolute authority over routing, retries, and state mutation; the LLM operates strictly as
a reasoning engine within individual nodes. **The graph calls agents — not the other way around.**

---

## 2. Command Catalog Mapping

### 2.1 `agent audit`

- **Group:** Audit Group (`audit_agent`)
- **Persona:** Vigilant Auditor ("Trust nothing")
- **Output Schemas:**
  - `AuditReport`: `package_path`, `summary`, `stats`, `file_results`
  - `AuditStats`: `total_files_analysed`, `total_files_skipped`, `total_findings`, `blocker_count`, `critical_count`
- **Tool Usage:** Tier 2 `audit_package` for broad scanning. Granular file discovery via Tier 3
  `list_files` and `process_batch` agent-local tools.
- **Role:** Sub-agent controls reasoning; orchestrator controls I/O. Produces structured
  `AuditFinding` objects (`rule_id`, `severity`, `code_snippet`).

### 2.2 `agent fix`

- **Group:** Fix Group (`fixer_agent`)
- **Persona:** Mechanic ("Fix only the violation")
- **Output Schemas:**
  - `FixerReport`: `patches`, `unresolved_violations`, `tier_used`
  - `FilePatch`: `file_path`, `original_snippet`, `proposed_snippet`, `rationale`
- **Tool Usage:** Deeply integrated with `violation_writer.py` service for status updates and
  deduplication.
- **Role:** Receives pre-read file contents and violation strings. Generates precise code patches.

### 2.3 `eval gate`

- **Group:** Validate Group (`validation_agent`)
- **Persona:** Guard ("Reject on ANY failed check")
- **Output Schemas:** `ValidationReport` — `status` (`APPROVED`/`REJECTED`), `violations`, `rationale`
- **Tool Usage:** Operates at `ModelTier.STANDARD` within the `GuardNode` of the Autopilot Graph.
- **Role:** Final automated gate. A `REJECTED` status triggers a retry loop, routing state back to
  `LogicDraftNode`. Span-based evaluation via `EvaluatorContext.span_tree` (see `08-evals.md`).

### 2.4 `agent map`

- **Group:** Map Group (`map_agent`)
- **Persona:** Cartographer
- **Output Schemas:** `MapReport` — `package_path`, `features`, `relationships`, `summary`
- **Tool Tier:** Tier 2 (Searchable) via `map_codebase`
- **Role:** Provides codebase awareness (`FeatureLocation`/`FileRelationship`) to downstream tasks.

### 2.5 `agent design` / `agent planning`

- **Group:** Document Group (`task_agent`)
- **Persona:** Architect
- **Output Schemas:** `DecompositionReport` — `feature_description`, `tasks`, `identified_blockers`, `estimated_complexity`
- **Tool Tier:** Tier 2 (Work namespace) via `task_decompose_feature`
- **Reasoning mode:** `agent design` → Bounded-ToT; `agent planning` → ReAct 2
- **Role:** Decomposes features into sequenced TDD tasks.

### 2.6 `eval test`

- **Group:** Validate Group (`sentry_agent`)
- **Persona:** Sentry
- **Output Schemas:** `SentryReport` — `test_cases`, `summary`, `framework`
- **Tool Tier:** Tier 3 (SentryNode internal)
- **Role:** Drafts failing test proposals *before* implementation. Operates at `ModelTier.MICRO`.

### 2.7 `agent research`

- **Group:** Ideation Lifecycle
- **Core Agents:** `auditor` / `scribe`
- **Reasoning Mode:** Bounded Tree-of-Thought
- **Tool Tier:** Tier 2 (Searchable)

### 2.8 `workflow start`

- **Group:** Profile-selected multi-agent workflow
- **Core Agents:** Router-determined (reads `WorkflowPlan` from `router_agent`)
- **Reasoning Mode:** Profile-specific (see `02-workflows.md`)
- **Current state:** Blocked on Task 026 completion for full implementation. Compatibility path
  via `run_subagent_workflow` available in the interim.

---

## 3. Reasoning Patterns by Lifecycle Stage

| Pattern | Flow | Application | Hard Constraints |
|---------|------|-------------|-----------------|
| **ReAct-Challenge** | plan → re-think → design → execute | Default (Autopilot Graph) | Mandatory self-challenge step |
| **Bounded Tree-of-Thought** | observe → branch → prune → expand → decide | Architecture / Security | Width: 3, Depth: 2, Budget: 500 tokens |
| **ReAct 2** | plan → confirm/improve/drop → execute | Implementation Planning | Iterative review of prior drafts |

**Selection logic:**

- Low ambiguity → ReAct 1
- Draft iteration → ReAct 2
- High-stakes architecture → Bounded-ToT (mandatory for Security Hardening, Disaster Recovery)

---

## 4. Evaluation Strategy and Pydantic Evals Integration

### 4.1 Span-Based Evaluation Framework

The `eval gate` command uses `pydantic-evals` to inspect the internal logic of agent runs via
OpenTelemetry traces (Logfire → `EvaluatorContext.span_tree`). This validates *how* an agent
reached a conclusion — not just the final string output.

```python
# Example: verify security tool was called before patch was approved
from pydantic_evals.evaluators import HasMatchingSpan

has_scan = HasMatchingSpan(query={"name": "sql_injection_scan"})
```

### 4.2 Evaluator Implementations

- **Deterministic:** Binary/Scalar checks — `EqualsExpected`, `MaxDuration`, `IsInstance`
- **Non-deterministic:** `LLMJudge` (rubric-based assessment for subjective quality)
- **Span-based:** `HasMatchingSpan`, or custom `Evaluator` subclass reading `ctx.span_tree`

### 4.3 The Reflection Loop

Pydantic AI automatically self-corrects when structured output fails schema validation. The
efficacy of this loop is driven by high-quality `Field(description="...")` annotations — these
are the exact instructions the model reads to correct its reasoning at runtime.

---

## 5. Tool-Service Boundary Analysis

### 5.1 Outcome-Oriented Tool Design

MCP tools must be "outcome-oriented" to preserve the context window and ensure deterministic
execution of complex logic.

```python
# Good (outcome-oriented):
task_decompose_feature(project_id, feature_description) → DecompositionReport
# Encapsulates task dependencies and complexity estimation in one call.

# Avoid (primitive-leaking):
db_create_node(label, props)
db_get_node(id)
db_link_nodes(from_id, to_id, rel)
# Three primitives the caller must manually orchestrate.
```

### 5.2 Service Layer Encapsulation

Complexity is pushed to `services/` (e.g., `violation_writer.py`, `TextEmbedService`). MCP tools
remain "thin wrappers" responsible only for argument marshalling. This decoupling allows
`services/` to be the primary unit test target without LLM or MCP transport overhead.

### 5.3 Dependency Injection Pattern

`RunContext[deps_type]` provides type-safe access to services while maintaining provider agnosticism.

```python
async def analyze_code_structure(
    ctx: RunContext[CodebaseDeps],
    query: str
) -> AnalysisResult:
    embedder = ctx.deps.text_embed_service  # injected service
    skills = ctx.deps.skills_content        # injected skill fragment
    vector = await embedder.embed_text(query)
    return await ctx.deps.search_service.hybrid_search(vector)
```

---

## 6. Technical Summary Table

| Command | Agent Group | Core Agent | Default Reasoning | Primary Tier |
|---------|-------------|------------|-------------------|--------------|
| `agent audit` | Audit | `audit_agent` | ReAct-Challenge | Tier 2 (Searchable) |
| `agent fix` | Fix | `fixer_agent` | ReAct-Challenge | Tier 2 (Service-backed) |
| `eval gate` | Validate | `validation_agent` | ReAct-Challenge | Tier 2 (Agent-local T3 tools) |
| `agent map` | Map | `map_agent` | ReAct-Challenge | Tier 2 (Searchable) |
| `agent design` | Document | `task_agent` | Bounded-ToT | Tier 2 (Work Namespace) |
| `eval test` | Validate | `sentry_agent` | ReAct-Challenge | Tier 3 (SentryNode) |
| `agent research` | Ideation | `auditor`/`scribe` | Bounded-ToT | Tier 2 (Searchable) |
| `agent planning` | Development | `router`/`scribe` | ReAct 2 | Tier 1 (Always loaded) |
| `workflow start` | Profile-selected | Router-determined | Profile-specific | Tier 2 |
| `toolchain python` | — | Allowlisted shell | n/a | Tier 2 outcome wrapper |
| `toolchain go` | — | Allowlisted shell | n/a | Tier 2 outcome wrapper |
| `python repl` | — | CodeMode snippet | n/a | Tier 1 (diagnostic) |
