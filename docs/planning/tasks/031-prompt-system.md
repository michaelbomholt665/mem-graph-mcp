# Task 031: Prompt System — Dynamic Context Injection and Cache Optimization

**Status:** Planning
**Priority:** High
**Blocked by:** Task 029 (Base Agent Architecture), Task 030 (Workflow Infrastructure)
**Blocks:** Task 032 (Skills)
**Complexity:** MEDIUM

## Problem Statement

Prompts are currently split across three layers (personas, agent functions, registry) but the system is not optimizing for prompt caching effectively. Static persona content could be cached as a prefix, but it's entangled with dynamic content. Workflow-stage prompts are generic and don't inject reasoning-mode guidance. Persona OCEAN scores are included verbatim in prompts, wasting tokens on numbers instead of natural language.

The goal is to:
1. **Establish a three-layer architecture** that maximizes provider-side prompt cache hits.
2. **Render OCEAN scores** as natural-language descriptors.
3. **Inject workflow reasoning modes** into stage prompts so agents self-apply correct strategy.
4. **Formalize the PROMPT_REGISTRY** with named entries for all 29 planned workflows.
5. **Make conditional branching explicit** in agent system_prompt functions rather than buried in strings.

## Goals

1. **Optimize prompt caching:** Layer 1 (persona base) is cacheable prefix; Layer 2 (dynamic context) is cache tail.
2. **Replace OCEAN floats:** Convert `0.83` to `"methodical, precise, reserved"` — more tokens but better model calibration.
3. **Create reasoning-mode templates:** Named entries for REACT_CHALLENGE, REACT_2, BOUNDED_TOT, COT in PROMPT_REGISTRY.
4. **Populate PROMPT_REGISTRY:** 29 entries (one per planned workflow stage) + core templates.
5. **Formalize conditional prompts:** Each agent's `@agent.system_prompt` explicitly branches on deps values with clear `if/else` blocks.
6. **Dynamic tool injection:** Build tool lists from `ctx.deps` instead of hardcoding tool names in prompts.

## Non-Goals

- Changing the Pydantic AI prompt-cache framework itself.
- Building a prompt versioning system (that's future iteration).
- Adding LLM-powered prompt optimization (GEPA does that in Task 026).

## Current State

### Three-Layer Architecture (Partially Implemented)

| Layer | Current | Ideal |
|-------|---------|--------|
| **Layer 1 — Personas** | `resources/personas.py` — 12 `Persona` objects | Cacheable prefix; no dynamic content |
| **Layer 2 — Dynamic** | `@agent.system_prompt` functions | Dynamic tail; injected from RunContext deps |
| **Layer 3 — Registry** | `resources/prompts.py` — `PROMPT_REGISTRY` | Named workflow-stage templates (skeleton) |

### Persona Issues

- OCEAN scores included verbatim: `Openness=0.78, Conscientiousness=0.91, ...`
- Should render as: `"Open to new ideas (0.78), methodical and conscientious (0.91)"`
- Saves tokens while preserving calibration intent.

### Dynamic Prompt Functions (Partial Examples)

**Audit agent (good pattern):**
```python
@audit_agent.system_prompt
async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
    persona_instr = AUDITOR_PERSONA.get_system_instructions()
    skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
    rules_block  = _format_rules_for_prompt(ctx.deps.rules)
    workflow     = "self-guided" if not ctx.deps.extra_file_context else "pre-loaded"
    return f"""{persona_instr}
## Domain Knowledge
{skills_block}
## Audit Rules
{rules_block}
## Your Task
1. [branched on workflow mode]
...
"""
```

**Issues:**
- Tool names hardcoded: `"call list_files"` instead of built from deps.
- Reasoning mode not injected.
- No explicit `if/else` — logic buried in ternary operators.

### PROMPT_REGISTRY (Skeleton)

Current entries:
- `sync_context`
- `plan_feature`
- `run_audit`
- `close_session`
- `workflow_agent` (reused for all managed-workflow stages)
- `agent_builder_discovery`
- `agent_builder_update`

**Issues:**
- Generic `workflow_agent` used for 9 stages; needs 29 specific templates.
- No reasoning-mode variants.
- Tool names hardcoded instead of dynamic.

### Conditional Branching Pattern (Needs Formalization)

Current (okay, but could be clearer):
```python
mode_note = (
    "Produce a workflow_plan because the caller requested subagent_workflow."
    if ctx.deps.workflow_mode == "subagent_workflow"
    else "Do not produce a workflow_plan."
)
```

Better pattern:
```python
if ctx.deps.workflow_mode == "subagent_workflow":
    mode_instructions = """Produce a workflow_plan with...
    """
else:
    mode_instructions = """Do not produce a workflow_plan. Focus on...
    """
```

## Target Files

### Modifications

```
src/mem_graph/resources/personas.py
  - Update Persona.get_system_instructions() to render OCEAN scores as natural language
  - Add Persona.get_ocean_descriptor(open, conscient, extrav, agreeable, neurot) -> str

src/mem_graph/resources/prompts.py
  - Expand PROMPT_REGISTRY with 29 workflow-specific entries
  - Add reasoning-mode template variants (REACT_CHALLENGE, REACT_2, BOUNDED_TOT, COT)
  - Add helper function: build_tool_list(deps) -> str to dynamically build tool names
  - Add helper: get_reasoning_mode_guidance(mode: str) -> str

src/mem_graph/agents/orchestrator_agent.py
  - Update @orchestrator_agent.system_prompt to use explicit if/else blocks
  - Inject reasoning_mode from deps if available

src/mem_graph/agents/router_agent.py
  - Update @router_agent.system_prompt to use explicit if/else for workflow_mode
  - Inject reasoning_mode guidance

src/mem_graph/agents/audit/audit_agent.py
  - Update @audit_agent.system_prompt to dynamically build tool list
  - Use explicit if ctx.deps.mode == "preloaded" blocks
  - Inject reasoning_mode from WorkflowProfile if available

src/mem_graph/agents/audit/rule_injector_agent.py
  - Update prompts to use dynamic rule formatting

src/mem_graph/agents/document/decision_agent.py
  - Update @decision_agent.system_prompt with explicit if/else on extra_file_context
  - Inject reasoning_mode guidance

src/mem_graph/agents/document/task_agent.py
  - Update @task_agent.system_prompt with reasoning_mode injection

src/mem_graph/agents/document/scribe_agent.py
  - Update @scribe_agent.system_prompt to use dynamic context

src/mem_graph/agents/document/triage_agent.py
  - Update @triage_agent.system_prompt for deduplication logic injection

src/mem_graph/agents/fix/fixer_agent.py
  - Update @fixer_agent.system_prompt with reasoning_mode guidance
  - Inject violation context from deps

src/mem_graph/agents/map/map_agent.py
  - Update @map_agent.system_prompt with reasoning_mode injection

src/mem_graph/agents/map/chat_agent.py
  - Update @chat_agent.system_prompt for memory integration

src/mem_graph/agents/map/diagram_agent.py
  - Update @diagram_agent.system_prompt for C4 scope injection

src/mem_graph/agents/validate/sentry_agent.py
  - Update @sentry_agent.system_prompt with framework detection
  - Inject reasoning_mode guidance

src/mem_graph/agents/validate/validation_agent.py
  - Update @validation_agent.system_prompt with check list injection

src/mem_graph/agents/builder/agent_builder.py
  - Update @agent_builder.system_prompt with spec format injection
```

### New Files

```
src/mem_graph/resources/prompts_evals.py
  - Store eval-specific prompt variations for scorer calibration

docs/planning/design/prompts/prompt-caching-strategy.md
  - Explain three-layer architecture and cache hit optimization
  - Document persona rendering strategy
  - Provide reasoning-mode injection examples
```

## Implementation Phases

### Phase 1: Refactor Personas for Natural Language (Sprint 1)

**Add OCEAN descriptor renderer:**
- [ ] Create helper in `personas.py`:
  ```python
  OCEAN_DESCRIPTORS = {
      (0.0, 0.2): ("close-minded", "closed-minded", "resistant to change"),
      (0.2, 0.4): ("practical", "conventional", "prefers routine"),
      (0.4, 0.6): ("balanced", "flexible", "adaptive"),
      (0.6, 0.8): ("imaginative", "curious", "open to new ideas"),
      (0.8, 1.0): ("visionary", "intellectually curious", "loves exploration"),
  }

  def render_ocean_trait(value: float, trait: str) -> str:
      """Convert OCEAN score to natural language descriptor."""
      score_range = next((k for k in OCEAN_DESCRIPTORS if k[0] <= value <= k[1]), (0, 1))
      descriptors = OCEAN_DESCRIPTORS[score_range]
      trait_name = {
          "openness": "ideas",
          "conscientiousness": "detail-oriented",
          "extroversion": "social",
          "agreeableness": "cooperative",
          "neuroticism": "emotional",
      }[trait.lower()]
      return descriptors[0]  # First descriptor; could randomize for variety
  ```

- [ ] Update `Persona.get_system_instructions()` to use natural language:
  ```python
  def get_system_instructions(self) -> str:
      ocean_traits = (
          f"{render_ocean_trait(self.openness, 'openness')}, "
          f"{render_ocean_trait(self.conscientiousness, 'conscientiousness')}, "
          f"{render_ocean_trait(self.extroversion, 'extroversion')}, "
          f"{render_ocean_trait(self.agreeableness, 'agreeableness')}, "
          f"{render_ocean_trait(self.neuroticism, 'neuroticism')}"
      )
      return f"""You are {self.name}, a {self.role}.

  {self.description}

  Your personality is characterized by being: {ocean_traits}.

  {self.base_instructions}
  """
  ```

- [ ] Test that persona preambles are identical across runs (reproducible randomization if needed).

### Phase 2: Expand PROMPT_REGISTRY with Workflow-Specific Entries (Sprint 1–2)

**Add reasoning-mode templates:**
- [ ] Create named entries in `prompts.py`:
  ```python
  REASONING_REACT_CHALLENGE = """
  Use the ReAct-Challenge pattern:
  1. **Plan**: Develop a detailed step-by-step approach.
  2. **Challenge**: Ask yourself: "What could go wrong? Missing context? Unstated constraints?"
  3. **Decide**: If the challenge reveals a flaw, revise the plan. Otherwise, proceed.
  4. **Design & Execute**: Implement the plan with detailed reasoning at each step.
  """

  REASONING_BOUNDED_TOT = """
  Use Bounded Tree-of-Thought:
  1. **Observe**: State the problem clearly.
  2. **Branch**: Propose ≤3 distinct candidate approaches.
  3. **Score**: Evaluate each against: (a) Architectural fit, (b) Context availability, (c) Tool budget, (d) Circularity.
  4. **Prune**: Eliminate approaches with low scores.
  5. **Expand**: Develop the winning approach in detail.
  6. **Decide**: Commit to the best approach with reasoning.
  """

  REASONING_REACT_2 = """
  Use ReAct-2 pattern (for iterating on prior work):
  1. **Review**: Examine the prior decision or draft provided.
  2. **Decide**: Confirm, improve, or drop it entirely.
  3. **Design & Execute**: Proceed with the chosen direction.
  """

  REASONING_COT = """
  Use Chain-of-Thought:
  1. Run N candidate reasoning paths in parallel.
  2. At each step, evaluate which path is strongest.
  3. Carry only the best path forward into the next step.
  4. Conclude with the best reasoning chain.
  """

  PROMPT_REGISTRY = {
      # Reasoning modes
      "reasoning.react_challenge": REASONING_REACT_CHALLENGE,
      "reasoning.react_2": REASONING_REACT_2,
      "reasoning.bounded_tot": REASONING_BOUNDED_TOT,
      "reasoning.cot": REASONING_COT,

      # Workflow stages (29 total, example subset)
      "stage.feature_implementation.sentry": "...",
      "stage.feature_implementation.logic_draft": "...",
      "stage.refactor.mapping": "...",
      "stage.security_hardening.audit": "...",
      # ... etc

      # Existing entries (keep unchanged)
      "sync_context": SYNC_CONTEXT_PROMPT,
      "plan_feature": PLAN_FEATURE_PROMPT,
      ...
  }
  ```

- [ ] Define all 29 workflow-stage templates:
  ```python
  # For each workflow in WorkflowRegistry:
  FEATURE_IMPLEMENTATION_SENTRY_PROMPT = """You are the Sentry — test architect. Your task: propose failing test cases that would fail before the feature is implemented."""
  FEATURE_IMPLEMENTATION_LOGIC_DRAFT_PROMPT = """You are the Mechanic — code fixer. Your task: implement the feature to make the Sentry's tests pass."""
  # ... etc
  ```

### Phase 3: Formalize Conditional Branching (Sprint 2)

**Update agent system_prompt functions to use explicit if/else:**
- [ ] Audit agent example:
  ```python
  @audit_agent.system_prompt
  async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
      persona_instr = AUDITOR_PERSONA.get_system_instructions()
      skills_block = ctx.deps.skills_content or "No additional domain knowledge provided."
      rules_block = _format_rules_for_prompt(ctx.deps.rules)

      # Explicit branching on mode
      if ctx.deps.mode == "preloaded":
          task_instructions = """
          1. Review the pre-loaded file content provided above.
          2. Apply the audit rules to each file.
          3. Report your findings in the specified output format.
          """
      else:  # standalone
          task_instructions = """
          1. Call list_files to discover files in the package.
          2. Call process_batch iteratively to read and analyze files.
          3. Apply the audit rules to each file.
          4. Call finalize_report to produce the final AuditReport.
          """

      # Inject reasoning mode if available
      reasoning_hint = ""
      if hasattr(ctx.deps, 'reasoning_mode') and ctx.deps.reasoning_mode:
          reasoning_hint = f"\n\n{PROMPT_REGISTRY.get(f'reasoning.{ctx.deps.reasoning_mode}', '')}"

      return f"""{persona_instr}

  ## Domain Knowledge
  {skills_block}

  ## Audit Rules
  {rules_block}

  ## Your Task
  {task_instructions}
  {reasoning_hint}
  """
  ```

- [ ] Apply same pattern to all 12 agents.

### Phase 4: Dynamic Tool List Injection (Sprint 2–3)

**Add helper function:**
- [ ] Create `prompts.py`:
  ```python
  def build_tool_names_for_prompt(
      tool_names: list[str],
      deps: Any,
  ) -> str:
      """Dynamically generate tool list for prompt."""
      tools_md = "- " + "\n- ".join(tool_names)
      return f"""
  ## Tools at Your Disposal
  You can call the following tools:
  {tools_md}
  """
  ```

- [ ] Update agents to call this helper:
  ```python
  @audit_agent.system_prompt
  async def build_system_prompt(ctx: RunContext[AuditDependencies]) -> str:
      # Instead of hardcoding tool names:
      # tools_section = """
      # You can call:
      # - list_files
      # - process_batch
      # """

      # Use dynamic builder:
      available_tools = ["list_files", "process_batch", "finalize_report"]
      tools_section = build_tool_names_for_prompt(available_tools, ctx.deps)

      return f"""..{tools_section}..."""
  ```

### Phase 5: Workflow-Specific Stage Prompt Injection (Sprint 3)

**Update workflow runtimes to inject stage-specific prompts:**
- [ ] Modify workflow nodes to use PROMPT_REGISTRY:
  ```python
  class LogicDraftNode(BaseNode[...]):
      async def run(self, ctx: GraphRunContext[...]) -> ...:
          # Get stage prompt from registry
          stage_key = f"stage.{ctx.state.workflow_key}.logic_draft"
          stage_prompt = PROMPT_REGISTRY.get(stage_key, WORKFLOW_AGENT_PROMPT)

          # Inject reasoning mode
          if ctx.state.reasoning_mode:
              reasoning_key = f"reasoning.{ctx.state.reasoning_mode}"
              reasoning_guidance = PROMPT_REGISTRY.get(reasoning_key, "")
              stage_prompt = f"{stage_prompt}\n\n{reasoning_guidance}"

          # Create deps with injected prompt context
          deps = FixerDependencies(
              ...,
              stage_instructions=stage_prompt,
              reasoning_mode=ctx.state.reasoning_mode,
          )

          result = await fixer_agent.run(
              CUSTOM_PROMPT_OVERRIDE or stage_prompt,
              deps=deps,
          )
  ```

- [ ] Add `stage_instructions` and `reasoning_mode` fields to all agent deps dataclasses.

### Phase 6: Documentation and Validation (Sprint 3–4)

- [ ] Create `docs/planning/design/prompts/prompt-caching-strategy.md`:
  ```markdown
  # Prompt Caching Strategy

  ## Three-Layer Architecture

  **Layer 1 — Cacheable Prefix (Personas)**
  - `Persona.get_system_instructions()` output
  - Static; cached by provider for 24 hours
  - Example: `You are Vigilant, a Security & Quality Auditor. Open to ideas, methodical and conscientious, ...`

  **Layer 2 — Dynamic Tail (Agent System Prompt Function)**
  - `@agent.system_prompt` output from RunContext deps
  - Domain knowledge, rules, task-specific context
  - Varies per run; NOT cached

  **Layer 3 — Workflow Registry (Named Templates)**
  - Stage-specific prompts for planned workflows
  - Reasoning-mode guidance
  - Reusable across workflow runs

  ## Expected Cache Hit Rates

  - Single-agent calls: 60–70% hit rate (persona + skills cached)
  - Workflow runs: 50–60% hit rate (multiple agents, shared base)
  - High-volume same-agent calls: 80%+ hit rate
  ```

- [ ] Add validation script `scripts/validate_prompt_caching.py`:
  ```python
  def check_prompt_caching():
      """Validate that prompts follow three-layer pattern."""
      # Check: All personas render without OCEAN numbers
      # Check: All agent system_prompt functions use ctx.deps
      # Check: All workflow nodes inject reasoning_mode
      # Check: All hardcoded tool names are gone
  ```

- [ ] Run validation on all agent files.

## Acceptance Criteria

1. **OCEAN scores rendered naturally:** `Persona.get_system_instructions()` outputs natural language, not floats.
2. **PROMPT_REGISTRY expanded:** 29+ workflow-specific entries; reasoning-mode variants defined.
3. **Conditional branching explicit:** All agent `@agent.system_prompt` functions use clear `if/else` blocks, not ternary operators.
4. **Dynamic tool injection:** Tool lists built from `ctx.deps`, not hardcoded.
5. **Reasoning-mode guidance injected:** Stage prompts include relevant reasoning template from PROMPT_REGISTRY.
6. **No regression:** Existing agents produce equivalent outputs (minor formatting changes acceptable).
7. **Caching strategy validated:** Custom validation script confirms compliance.

## Test Plan

```bash
# Test persona rendering
uv run pytest tests/resources/test_personas.py -q

# Test PROMPT_REGISTRY expansion
uv run pytest tests/resources/test_prompts.py -q

# Test dynamic prompt injection
uv run pytest tests/agents/test_system_prompts.py -q

# Test reasoning mode injection
uv run pytest tests/workflows/test_reasoning_prompt_injection.py -q

# Regression on agent outputs
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/agents/ -q

# Validate caching compliance
python scripts/validate_prompt_caching.py

# Broad gate
MEM_GRAPH_LOGFIRE_ENABLED=false OTEL_SDK_DISABLED=true \
  uv run pytest tests/ -q
```

## Dependencies

- Task 029 (Base Agent Architecture) — agent deps structure must be stable.
- Task 030 (Workflow Infrastructure) — workflow registry and reasoning modes must exist.

## Notes

- Prompt cache hit rates should be measured after deployment; these are estimates based on industry benchmarks.
- GEPA (Task 026) will further optimize prompts post-deployment.
- Workflow-stage prompts can be A/B tested independently after this task lands.
