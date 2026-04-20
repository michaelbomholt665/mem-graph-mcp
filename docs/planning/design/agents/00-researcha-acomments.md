# 00 — Research Notes: Evals, Tools, and Workflows

> **Source:** Gap analysis from the `6e0f4bf2` session. Raw research output from AI assistant,
> restructured for permanent reference. See `00-1-report.md` for the Command Catalog mapping and
> `00-2-GEPA.md` for the GEPA pattern deep-dive.

---

## Index

1. [Evals: Span-Based Evaluation and Logfire Integration](#1-evals-span-based-evaluation-and-logfire-integration)
2. [Tools: Tier 1 Visibility and Curation Decisions](#2-tools-tier-1-visibility-and-curation-decisions)
3. [Workflows: Implementation Order and Agent Gaps](#3-workflows-implementation-order-and-agent-gaps)
4. [Span Tree — How It Validates Reasoning Paths](#4-span-tree--how-it-validates-reasoning-paths)
5. [Custom Span-Based Evaluator — Implementation Pattern](#5-custom-span-based-evaluator--implementation-pattern)
6. [Logfire Trace Access and Querying](#6-logfire-trace-access-and-querying)
7. [Tool Design: Curation and Tier 3 Strategy](#7-tool-design-curation-and-tier-3-strategy)
8. [Logic Gotchas: Detecting Circular Imports](#8-logic-gotchas-detecting-circular-imports)
9. [Sub-Agent Delegation: The Orchestrator Guardrail](#9-sub-agent-delegation-the-orchestrator-guardrail)
10. [Command Catalog Integration Mapping](#10-command-catalog-integration-mapping)

---

## 1. Evals: Span-Based Evaluation and Logfire Integration

Research into span-based patterns reveals the integration is centred on **OpenTelemetry traces**
captured via Pydantic Logfire.

- **Logfire Trace Access:** The `EvaluatorContext` in `pydantic-evals` exposes a **`span_tree`**
  attribute. This is a graph where each node corresponds to an OpenTelemetry span recorded during
  task execution, including timing and custom spans.
- **Trace-Assertion Extension:** Span-Based Evaluators are designed to analyse "reasoning paths"
  rather than just final outputs. This allows the system to detect "right answer, wrong path"
  regressions by asserting on span attributes.
- **Implementation Pattern:** The intended pattern involves fetching the Logfire trace after a run
  and using it to verify internal agent behaviours, such as specific tool calls or execution flows.
  This ensures eval assertions are aligned with real-world production telemetry.
- **Built-in shortcut:** `HasMatchingSpan` — a built-in evaluator that checks if the `span_tree`
  contains a span matching a specific query. Use this before writing a custom evaluator.

---

## 2. Tools: Tier 1 Visibility and Curation Decisions

The goal for Tier 1 is a maximum of **5–8 tools** that are always visible and solve complete
outcomes.

**Confirmed Tier 1 tools:**
- `memory_recall` — Session/Graph memory
- `memory_capture_session` — Session/Graph memory
- `confirm_action` — Human-in-the-loop gate
- `request_human_approval` — Human-in-the-loop gate

**Promotion candidates (usage-data pending):**
- `memory_search` — frequent enough to justify default visibility
- `conversation_list` — high usage in interactive sessions

**Demotion decisions (ruthless curation):**
- Filesystem tools (`file_read`, `file_grep`, etc.) — demote from Tier 2 → **Tier 3**
  (Invisible). They are granular primitives for agents, not user-facing actions.
- Low-level DB operations in `tools/graph/graph_queries.py` — demote to **Tier 3**; expose only
  outcome-level tools like `graph_get_project_health` at Tier 2.

**Key principle:** "One tool equals one agent story." Hiding granular primitives (Tier 3) shifts
orchestration burden from expensive LLM calls to fast, deterministic Python code.

---

## 3. Workflows: Implementation Order and Agent Gaps

The 29 planned workflows split into two groups based on agent availability.

### Ready for Immediate Implementation (existing agent roster)

Uses `auditor`, `scribe`, `fixer`, `router`, `mapper`, `sentry`, `validation`, `task`,
`decision` agents.

**Highest priority:**
- `feature_implementation` — highest-value addition for current roster
- `refactor` — second-highest priority

**Other ready workflows:**
`research`, `feature_design`, `adr_authoring`, `schema_design`, `api_contract_design`,
`project_scaffold`, `dependency_audit`, `ci_setup`, `security_hardening`,
`performance_profiling`, `docs_generation`, `changelog_authoring`, `onboarding_docs`,
`release_preparation`, `deployment_validation`, `codebase_migration`, `code_skeptic`,
`utility_extraction`

### Blocked by Missing/Incomplete Agents

| Workflow | Blocker | Reason |
|----------|---------|--------|
| `idea_capture` | `chat_agent` missing | Requires interactive discovery |
| `requirements_elicitation` | `chat_agent` missing | Requires interactive discovery |
| `architecture_design` | `diagram_agent` incomplete | Needs C4 Mermaid diagram generation |
| `feature_design` | `diagram_agent` incomplete | Partially; can run without diagram node |
| `command_design` | Unclear | `fixer`/`scribe` needed, but lifecycle coupling unclear |

---

## 4. Span Tree — How It Validates Reasoning Paths

The **`span_tree`** attribute on `EvaluatorContext` helps validate reasoning paths by providing a
graph of OpenTelemetry spans recorded during an agent's execution.

- **Internal Behaviour Analysis:** Captures every step including tool calls, timing, and custom spans.
- **"Right Answer, Wrong Path" Regressions:** Output-only evals miss cases where an agent arrives
  at the correct answer through flawed logic. Span-based evaluators fetch the Logfire trace and
  assert on span attributes to confirm the intended path was followed.
- **Multi-Step Logic Validation:** For complex agents, correctness depends on execution sequence.
  The span tree verifies the agent invoked tools in the correct order.
- **Production Alignment:** Built from OpenTelemetry traces (via Logfire), assertions align with
  telemetry actually seen in production.

---

## 5. Custom Span-Based Evaluator — Implementation Pattern

### Core Steps

1. **Inherit from `Evaluator`:** `class MyEval(Evaluator[InputsT, OutputT, MetadataT])`
2. **Define `evaluate` method:** accepts `ctx: EvaluatorContext` as sole argument
3. **Access `ctx.span_tree`:** iterate or query the graph of OTel spans
4. **Analyse reasoning paths:** assert on specific span attributes (tool called? retry count? etc.)
5. **Return result:** `bool`, `float`, `str` label, or `EvaluationReason`

### Configuration Requirements

- **Logfire/OpenTelemetry Integration:** Must be configured during task execution for `span_tree`
  to be populated.
- **Trace Identification:** `EvaluatorContext` captures `trace_id` and `span_id` automatically.

### Example — Built-in shortcut

```python
from pydantic_evals.evaluators import HasMatchingSpan

# Check that security scan tool was called before approving the patch
has_scan = HasMatchingSpan(query={"name": "sql_injection_scan"})
```

---

## 6. Logfire Trace Access and Querying

The primary API for accessing trace data within an evaluation is the **`span_tree`** attribute.

- **`EvaluatorContext`:** Every evaluator receives a context object containing `span_tree`.
- **`SpanTree` structure:** Graph where each node is an OpenTelemetry span. Includes timing,
  tool calls, and custom spans.
- **Trace identification:** Context captures `trace_id` and `span_id` from the agent run.

### Trace Assertions in pydantic-evals

- **`HasMatchingSpan`:** Built-in evaluator; checks if `span_tree` contains a matching span.
- **Custom evaluators:** Assert on span attributes for fine-grained internal behaviour verification.
- **Production alignment:** Assertions align with the telemetry seen in Logfire in production.

---

## 7. Tool Design: Curation and Tier 3 Strategy

Moving the bulk of 60–80 tools into **Tier 3 (Invisible)** prevents "context drowning."

- **Discovery and token costs:** Exposing 60+ tools consumes a massive portion of the 200K-token
  context window before any reasoning occurs.
- **Outcome-Oriented Tools:** Tier 1 goal = "one tool equals one agent story." Hiding primitives
  shifts orchestration from the LLM to deterministic Python.
- **Internal access:** Tier 3 tools remain fully accessible as building blocks for `@agent.tool`
  functions or within workflow nodes. No functionality is lost, just managed.

### Wrapper Pattern

Instead of raw file tools, agents use their own `@agent.tool` wrappers (`list_files`,
`process_batch`) which apply byte limits, extension filters, and scope constraints.

### Enhanced Search (Codebase-Aware)

- **Map Agent integration:** `map_agent` produces `FeatureLocation` and `FileRelationship` for
  codebase awareness.
- **Graph-Backed Search:** Code Symbol Graph in Ladybug; not raw `grep`.
- **`GraphContextService` recommendation:** Extract raw Cypher from `orchestrator_graph.py` into a
  service enabling searches for project health, symbol relationships, dependency maps.

---

## 8. Logic Gotchas: Detecting Circular Imports

Using the Ladybug SCC (Strongly Connected Components) extension detects the **Circular Import**
"architecture killer."

- **One-Way Dependency Graph:** The recommended structural prevention.
- **Refactoring Pattern:** If SCC flags a cycle, extract shared logic to a neutral third module
  (`common.py`, `models.py`) or use the `TYPE_CHECKING` pattern with quote notation.

---

## 9. Sub-Agent Delegation: The Orchestrator Guardrail

Limiting sub-agent spawning to the **Orchestrator** prevents "recursive delegation hazards."

- **Isolated Context:** Sub-agents cannot see the parent's full todo list and cannot spawn their
  own sub-agents.
- **Orchestration Role:** The Orchestrator is the central dispatcher for `SUBAGENT_REGISTRY`.
- **Clarification Loops:** Sub-agents cannot spawn help, but can use an `answer_subagent` pattern
  to ask the parent (Orchestrator) for clarification without breaking the delegation hierarchy.

---

## 10. Command Catalog Integration Mapping

The Command Catalog (Task 027) provides the "connective tissue" from theoretical agent personas to
a functional **Deep Agent** environment. Key mappings:

### Command → Agent Group

| CLI Command | Agent Group | Core Agent |
|-------------|-------------|------------|
| `agent audit` | Audit Group | `audit_agent` |
| `agent map` | Map Group | `map_agent` |
| `agent fix` | Fix Group | `fixer_agent` |
| `agent validate` | Validate Group | `validation_agent` |
| `agent document` | Document Group | `scribe_agent` |
| `eval gate` | Validate Group | `validation_agent` |
| `eval test` | Validate Group | `sentry_agent` |
| `workflow start` | Profile-selected | Router-determined |

### Command → Tier Mapping

| CLI Command | Tier | Notes |
|-------------|------|-------|
| `python repl` | Tier 1 (outcome) | Diagnostic code execution |
| `shell execute` | Tier 1 (outcome) | Gated allowlist |
| `toolchain go` / `toolchain python` | Tier 2 wrapper | Outcome-oriented; handles fmt+test+scan |
| `code parse` / `db migrate` | Tier 3 backing | Building blocks for agentic tasks |

### Eval Gate → Span Hook

The `eval gate` command executes fixture/CI/live/release eval gates. The `span_tree` attribute
in `EvaluatorContext` is what allows these gates to validate internal reasoning paths at runtime.
