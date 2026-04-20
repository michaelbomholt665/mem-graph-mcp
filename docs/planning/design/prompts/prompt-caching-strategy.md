# Prompt Caching Strategy

## Three-Layer Architecture

The prompt system uses a three-layer design to maximise provider-side cache hits.

| Layer | Source | Cacheability |
|-------|--------|--------------|
| **Layer 1 — Persona Prefix** | `Persona.get_system_instructions()` | ✅ Static; cacheable for 24 h |
| **Layer 2 — Dynamic Tail** | `@agent.system_prompt` functions | ❌ Varies per run; NOT cached |
| **Layer 3 — Registry Templates** | `PROMPT_REGISTRY` entries | ✅ Named; cacheable when stable |

### Layer 1 — Cacheable Persona Prefix

`Persona.get_system_instructions()` emits a deterministic string for a given persona.
OCEAN scores are rendered as natural-language descriptors (e.g. `"methodical, precise"`)
so the output is stable across runs and eligible for provider-side prefix caching.

**Example output (AUDITOR_PERSONA):**
```
You are Vigilant, Senior Security & Quality Auditor.
A meticulous, eagle-eyed specialist who finds hidden bugs and architectural flaws.
Your personality is characterized by being: curious, highly disciplined, reserved, pragmatic, emotionally stable.
Scan for bugs, leaks, and security issues with extreme precision. Trust nothing.
```

### Layer 2 — Dynamic Context Tail

Each agent's `@agent.system_prompt` function reads `ctx.deps` at runtime to inject:
- Domain knowledge (`skills_content`)
- Violation / decision context
- Pre-loaded file content (`extra_file_context`)
- Reasoning-mode guidance (`reasoning_mode`)

This layer is unique per run and thus NOT cached. Keeping it short maximises the
effective cache hit rate for the stable Layer 1 prefix.

### Layer 3 — Registry Templates

`PROMPT_REGISTRY` stores named, reusable templates:
- `reasoning.*` — ReAct-Challenge, ReAct-2, Bounded-ToT, CoT
- `stage.*` — 29 workflow-stage prompts (one per planned workflow stage)
- Legacy orchestrator-level prompts

Templates are static strings. They are injected into Layer 2 at runtime so the
dynamic tail carries all the context but at least the template part is stable.

---

## OCEAN Score Rendering

Before Task 031, OCEAN scores were interpolated verbatim:
```
Your personality is characterized by: Openness=0.78, ...
```

After Task 031, scores are rendered as natural-language descriptors:
```
Your personality is characterized by being: curious, highly disciplined, reserved, ...
```

Benefits:
- **Stability**: same persona → same descriptor string → cache hits.
- **Model calibration**: descriptors are more interpretable than raw floats.
- **Token efficiency**: shorter strings for equivalent information.

---

## Reasoning-Mode Injection

Reasoning mode is injected into Layer 2 by the agent's `@agent.system_prompt`
function when `ctx.deps.reasoning_mode` is non-empty:

```python
reasoning_hint = ""
if ctx.deps.reasoning_mode:
    reasoning_hint = f"\n\n## Reasoning Strategy\n{get_reasoning_mode_guidance(ctx.deps.reasoning_mode)}"
```

Available modes:
| Key | Pattern |
|-----|---------|
| `react_challenge` | Plan → Challenge → Decide → Execute |
| `react_2` | Review → Decide → Execute |
| `bounded_tot` | Observe → Branch (≤3) → Score → Prune → Expand → Decide |
| `cot` | N parallel paths → evaluate → carry best forward |

---

## Expected Cache Hit Rates

These are estimates based on industry benchmarks for prefix caching:

| Scenario | Estimated Hit Rate |
|----------|--------------------|
| Single-agent calls (same persona) | 60–70% |
| Workflow runs (multiple agents) | 50–60% |
| High-volume same-agent calls | 80%+ |

Cache hit rates should be measured after deployment with Logfire tracing enabled.

---

## Validation

Run `scripts/validate_prompt_caching.py` to check compliance:
```bash
python scripts/validate_prompt_caching.py
```

Checks performed:
1. All personas render without OCEAN floats.
2. All agent system_prompt functions read from `ctx.deps` (no hardcoded content).
3. All 29 workflow stage keys are present in `PROMPT_REGISTRY`.
4. All 4 reasoning-mode keys are present in `PROMPT_REGISTRY`.
