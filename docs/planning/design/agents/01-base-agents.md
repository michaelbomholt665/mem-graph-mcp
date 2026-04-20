# 01 — Base Agent Files

## Principle

Base agents are stateless, globally-instantiated service objects — analogous to FastAPI router instances. They must never accumulate runtime state themselves. All mutable context flows through typed `@dataclass` dependencies (`deps_type`) injected per-run via `RunContext`.

> **Context-window discipline:** Keep the static agent constructor minimal. Push all task-specific context into the `@agent.system_prompt` function, which is re-evaluated per run and sorted by the framework to maximise prompt-cache hit rates. A monolithic master prompt burns prefill tokens on every run regardless of relevance.

---

## Skills as Context, Not Strings

Every agent's `@dataclass` deps includes a `skills_content: str` field. This is currently a raw SKILL.md string. The **near-term direction** is code-based skills (see `04-skills.md`), but the interface stays the same — the skill system resolves a `SkillBundle` and injects its `prompt_fragment` into `skills_content` at call-time. No agent module needs to know how the string was produced.

> **Priority note:** Skills are secondary to getting workflows operational. The `skills_content: str` interface is stable and adequate for now. Code-based skill formalisation comes after the workflow layer is running.

---

## Current Agent Inventory

### Orchestration Layer (`agents/`)

| File | Agent | Persona | Output | Role |
|------|-------|---------|--------|------|
| `orchestrator_agent.py` | `orchestrator_agent` | — | `OrchestratorReport` | Batched sub-agent coordinator; dispatches to `SUBAGENT_REGISTRY` |
| `router_agent.py` | `router_agent` | `ROUTER_PERSONA` (Gateway) | `RouterDecision` | Intent classifier, model-tier selector, task decomposer |

`orchestrator_agent` registers six sub-agents at module load:
```
audit, security_audit, bug_audit, smell_audit, map, decision
```

`router_agent` produces `RouterDecision` with `ModelTier`, `concurrency`, `intent`, `sub_tasks`, and an optional `WorkflowPlan`. Uses `ModelTier.TURBO` — routing is a classification task, not a reasoning task.

---

### Audit Group (`agents/audit/`)

| File | Agent | Persona | Output |
|------|-------|---------|--------|
| `audit_agent.py` | `audit_agent` | `AUDITOR_PERSONA` (Vigilant) | `AuditReport` |
| `audit_agent.py` | `preloaded_audit_agent` | `AUDITOR_PERSONA` | `AuditReport` |
| `rule_injector_agent.py` | `rule_injector_agent` | `RULE_INJECTOR_PERSONA` (RuleLibrarian) | rule sets |
| `factory.py` | `build_audit_agent_bundle()` | — | `AuditBundle` |

`audit_agent` discovers and reads files itself via `list_files` / `process_batch` tools.
`preloaded_audit_agent` expects files pre-loaded into `extra_file_context` — it has **no** file-reading tools. The orchestrator controls I/O; the sub-agent controls reasoning.

`AuditDependencies`: `package_path`, `rules: list[AuditRule]`, `file_extension`, `skills_content`, `extra_file_context`, `file_results: list[FileAuditResult]`

---

### Document Group (`agents/document/`)

| File | Agent | Persona | Output |
|------|-------|---------|--------|
| `decision_agent.py` | `decision_agent` | `ARCHITECT_PERSONA` (Structure) | `ReviewReport` |
| `task_agent.py` | `task_agent` | `ARCHITECT_PERSONA` | `DecompositionReport` |
| `scribe_agent.py` | `scribe_agent` | `SCRIBE_PERSONA` (Scribe) | `ScribeReport` |
| `triage_agent.py` | `triage_agent` | `TRIAGE_PERSONA` (Dispatcher) | triage findings |

`decision_agent` compares injected `decisions: list[dict]` against source code, producing `DecisionReview` with `DriftStatus` (`HONOURED | DRIFTED | SUPERSEDED | UNVERIFIABLE`).

`task_agent` decomposes a feature description into a sequenced `Task` list with TDD phases (`planning → red → green → refactor → audit`), wiring dependencies by `task_id`.

---

### Fix Group (`agents/fix/`)

| File | Agent | Persona | Output |
|------|-------|---------|--------|
| `fixer_agent.py` | `fixer_agent` | `MECHANIC_PERSONA` (Mechanic) | `FixerReport` |

Receives pre-read `file_contents: dict[str, str]` and violation strings. Produces `FilePatch` objects (`original_snippet` → `proposed_snippet`) or marks violations unresolvable. Tier is set by `RouterDecision` at call-time, default `ModelTier.STANDARD`.

---

### Map Group (`agents/map/`)

| File | Agent | Persona | Output |
|------|-------|---------|--------|
| `map_agent.py` | `map_agent` | `MAPPER_PERSONA` (Cartographer) | `MapReport` |
| `chat_agent.py` | `chat_agent` | `CHAT_PERSONA` (Librarian) | conversational |
| `diagram_agent.py` | `diagram_agent` | — | diagram output |

`map_agent` produces `FeatureLocation` and `FileRelationship` lists. Output feeds `task_agent` (codebase awareness) and `decision_agent` (blast-radius context).

---

### Validate Group (`agents/validate/`)

| File | Agent | Persona | Output |
|------|-------|---------|--------|
| `sentry_agent.py` | `sentry_agent` | `SENTRY_PERSONA` (Sentry) | `SentryReport` |
| `validation_agent.py` | `validation_agent` | `GUARD_PERSONA` (Guard) | `ValidationReport` |

`sentry_agent` runs at `ModelTier.MICRO`. It only drafts failing test proposals before code changes land.
`validation_agent` runs at `ModelTier.STANDARD`. A `ValidationStatus.REJECTED` routes the orchestrator graph back to `LogicDraftNode` for a retry loop.

---

### Builder Group (`agents/builder/`)

| File | Description |
|------|-------------|
| `agent_builder.py` | `AGENT_BUILDER_PERSONA` (Builder). Designs project-specific helper-agent specs as validated YAML. Exposes `find_helper_agent_spec` / `list_helper_agent_specs` for orchestrator/router use. |

---

## Design Patterns in Use

**Stateless global instances:**
```python
audit_agent: Agent[AuditDependencies, AuditReport] = Agent(
    AGENT_MODEL, name="audit",
    deps_type=AuditDependencies, output_type=AuditReport,
    model_settings=config_model_settings(temperature=0.2, top_p=0.9),
    defer_model_check=DEFER_AGENT_MODEL_CHECK,
)
```

**Typed dependency injection:**
```python
@dataclass
class AuditDependencies:
    package_path: str
    rules: list[AuditRule] = field(default_factory=lambda: list(DEFAULT_RULES))
    skills_content: str = ""          # resolved from SkillBundle.prompt_fragment at call-time
    extra_file_context: str = ""      # pre-read block when orchestrator controls I/O
    file_results: list[FileAuditResult] = field(default_factory=list)
```

**Dynamic system prompt:**
```python
@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    ...
```

---

## Improvement Opportunities

| Issue | Recommendation |
|-------|---------------|
| `_decision_state` and `_task_state` are monkey-patched onto `RunContext` | Move accumulators into the `@dataclass` deps, not `ctx.__dict__` |
| `preloaded_audit_agent` is functionally identical to `audit_agent` with a different prompt branch | Use a single agent with `mode: Literal["standalone", "preloaded"]` in `AuditDependencies` |
| Fixer patches also monkey-patched on `ctx` (`ctx._fixer_patches`) | Same — move to `FixerDependencies` |
| `agents/discovery.py` role unclear | Document or consolidate with `router_agent` intent resolution |
