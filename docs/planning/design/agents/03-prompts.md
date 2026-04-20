# 03 — Prompts

## Principle

Prompts are never static strings baked into agent constructors. Every agent uses `@agent.system_prompt` — a function evaluated fresh on every run. The framework orders static constructor content first (cacheable prefix) and decorator-generated content second (dynamic tail), maximising provider-side prompt cache hits.

---

## Three Layers

```
Layer 1 — Persona base instructions   → stable, cached per-agent
Layer 2 — @agent.system_prompt fn     → dynamic, injected from RunContext[Deps]
Layer 3 — PROMPT_REGISTRY             → named workflow-stage templates
```

### Layer 1 — Persona (static prefix)

All 12 personas live in `resources/personas.py` → `PERSONA_REGISTRY`. `Persona.get_system_instructions()` renders a standard preamble:

```
You are {name}, {role}.
{description}
Your personality is characterized by: Openness=..., Conscientiousness=..., ...
{base_instructions}
```

The OCEAN scores provide model calibration; the `base_instructions` string is the critical behavioural constraint for that agent's role.

| Key | Name | Role | Temp | Key constraint |
|-----|------|------|------|---------------|
| `auditor` | Vigilant | Security & Quality Auditor | 0.2 | "Trust nothing." |
| `architect` | Structure | Principal Software Architect | 0.5 | "Evaluate against decisions. Prioritise modularity." |
| `triage` | Dispatcher | Triage & Classification | 0.3 | "Deduplicate. Assign correct severities." |
| `mapper` | Cartographer | System Mapping Specialist | 0.4 | "Build a mental map of dependencies." |
| `router` | Gateway | Intent Router & Decomposer | 0.3 | "Select lowest sufficient tier." |
| `rule_injector` | RuleLibrarian | Audit Rule Curator | 0.1 | "Prefer specific rules over broad ones." |
| `mechanic` | Mechanic | Violation Fixer | 0.4 | "Fix only the violation. Document the rationale." |
| `scribe` | Scribe | Documentation & Style Enforcer | 0.1 | "Never touch functional code." |
| `guard` | Guard | Post-Fix Validation | 0.2 | "Reject on ANY failed check." |
| `sentry` | Sentry | Test Architect | 0.2 | "Draft failing tests first." |
| `chat` | Librarian | Chat & Retrieval | 0.4 | "Ground every answer in graph context." |
| `agent_builder` | Builder | Helper-Agent Designer | 0.2 | "Prefer reviewable specs over generated code." |

### Layer 2 — Dynamic system prompt function

Each agent has one `@agent.system_prompt` function that reads `ctx.deps` and builds the context-specific tail:

```python
@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    persona_instr = AUDITOR_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    rules_block  = _format_rules_for_prompt(ctx.deps.rules)
    workflow     = "self-guided" if not ctx.deps.extra_file_context else "pre-loaded"
    ...
    return f"""{persona_instr}
## Domain Knowledge
{skills_block}
## Audit Rules
{rules_block}
...
"""
```

Pattern is consistent across all agents. The prompt function adapts its `## Your Task` section based on deps state — for example, `decision_agent` switches between a self-guided file-reading workflow and a pre-loaded batch workflow depending on whether `extra_file_context` is populated.

### Layer 3 — PROMPT_REGISTRY (workflow-stage templates)

Named string templates used by `workflow_graph.py` nodes to associate a prompt with each stage:

| Key | Purpose |
|-----|---------|
| `sync_context` | Re-orient agent to current project state via graph queries |
| `plan_feature` | Decompose feature requirements into tasks and diagrams |
| `run_audit` | Initiate quality & security audit pipeline |
| `close_session` | Synthesise progress and persist memory to graph |
| `workflow_agent` | Generic stage prompt for managed workflows |
| `agent_builder_discovery` | Discovery pass for project helper-agent design |
| `agent_builder_update` | Update existing helper-agent spec from eval evidence |

`get_sub_agent_instructions(persona_key, specific_task)` in `resources/prompts.py` combines a persona preamble with a task block for ad-hoc sub-agent spin-ups that don't go through the standard agent registry.

---

## Conditional Branching Inside Prompts

Prompts branch on `deps` values rather than spawning separate agent instances:

```python
# router_agent — adapts instructions based on workflow_mode
mode_note = (
    "Produce a workflow_plan because the caller requested subagent_workflow."
    if ctx.deps.workflow_mode == "subagent_workflow"
    else "Do not produce a workflow_plan."
)

# decision_agent — switches between guided and preloaded workflows
if ctx.deps.extra_file_context:
    workflow = "1. Review the supplied decisions against the pre-loaded files above.\n..."
else:
    workflow = "1. Call `list_files`. 2. Call `process_batch` iteratively. ..."
```

---

## Improvement Opportunities

| Issue | Recommendation |
|-------|---------------|
| `WORKFLOW_AGENT_PROMPT` is 3 lines used for multiple managed-workflow stages | Give the 29 planned workflows their own named prompt keys; the registry already supports it |
| OCEAN floats (`0.83`) are included verbatim in every prompt preamble | Render as natural-language descriptors ("methodical, precise, reserved") to save tokens while preserving calibration intent |
| `SYNC_CONTEXT_PROMPT` and `PLAN_FEATURE_PROMPT` reference specific tool names by string | These names drift when namespaces change; build them dynamically from `ctx.deps` instead |
| No per-workflow reasoning-mode hint is injected into the prompt | The `REACT_CHALLENGE`/`BOUNDED_TOT` mode selected by the workflow registry should appear in the stage prompt so agents self-apply the correct reasoning pattern |
