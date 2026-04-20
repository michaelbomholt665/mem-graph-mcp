# 037: Agent Instructions Migration (system_prompt → instructions)

**Status:** Complete
**Priority:** High

**Why**: The design doc `docs/planning/design/agents/09-instructions-tools.md` establishes `@agent.instructions` as the preferred pattern for agent system prompts due to token savings via prompt caching (instructions are never added to message history). The codebase currently uses `@agent.system_prompt` in 14 agents.

---

## Scope

### Files to Modify

| Agent | File | Pattern Used |
|------|-----|---------------|
| `audit_agent` | `src/mem_graph/agents/audit/audit_agent.py` | `@audit_agent.system_prompt` |
| `rule_injector_agent` | `src/mem_graph/agents/audit/rule_injector_agent.py` | `@rule_injector_agent.system_prompt` |
| `agent_builder_discovery_agent` | `src/mem_graph/agents/builder/agent_builder.py` | `@agent_builder_discovery_agent.system_prompt` |
| `decision_agent` | `src/mem_graph/agents/document/decision_agent.py` | `@decision_agent.system_prompt` |
| `scribe_agent` | `src/mem_graph/agents/document/scribe_agent.py` | `@scribe_agent.system_prompt` |
| `task_agent` | `src/mem_graph/agents/document/task_agent.py` | `@task_agent.system_prompt` |
| `triage_agent` | `src/mem_graph/agents/document/triage_agent.py` | `@triage_agent.system_prompt` |
| `fixer_agent` | `src/mem_graph/agents/fix/fixer_agent.py` | `@fixer_agent.system_prompt` |
| `chat_agent` | `src/mem_graph/agents/map/chat_agent.py` | `@chat_agent.system_prompt` |
| `map_agent` | `src/mem_graph/agents/map/map_agent.py` | `@map_agent.system_prompt` |
| `orchestrator_agent` | `src/mem_graph/agents/orchestrator_agent.py` | `@orchestrator_agent.system_prompt` |
| `router_agent` | `src/mem_graph/agents/router_agent.py` | `@router_agent.system_prompt` |
| `sentry_agent` | `src/mem_graph/agents/validate/sentry_agent.py` | `@sentry_agent.system_prompt` |
| `validation_agent` | `src/mem_graph/agents/validate/validation_agent.py` | `@validation_agent.system_prompt` |

**Total**: 14 agent definitions.

### Pattern Migration

Each agent uses:
```python
@<agent>.system_prompt
async def build_system_prompt(ctx: RunContext[Dependencies]) -> str:
    """..."""
    return f"""..."""
```

Must become:
```python
@<agent>.instructions
async def build_instructions(ctx: RunContext[Dependencies]) -> str:
    """..."""
    return f"""..."""
```

> Note: The decorator name changes from `.system_prompt` → `.instructions`. The function signature and return value remain identical.

---

## Approach

1. **Rename decorators**: `@<agent>.system_prompt` → `@<agent>.instructions` in all 14 files
2. **Rename functions**: `build_system_prompt` → `build_instructions` (optional, but recommended for clarity)
3. **Preserve behavior**: Keep the function body identical — return value format stays the same

### Alternative (per doc recommendation)

The design doc suggests using `instructions=` in the constructor for static content (Persona + Workflow) and `@agent.instructions` for dynamic session data. This is a larger refactor requiring:

1. Extract static Persona + Workflow strings to module-level constants
2. Pass as `instructions=` constructor argument
3. Keep `@agent.instructions` decorator only for dynamic `RunContext`-dependent content

**Recommended**: Start with the simple migration (decorator rename) to achieve immediate token savings. The constructor-based split can be a follow-up task.

---

## Verification

1. Run full test suite: `pytest` — all agents should function identically
2. Verify prompt caching behavior (no system_prompt in message history)

---

## Notes

- The simple rename preserves 100% backward compatibility
- The token savings come from Pydantic AI's handling of `@instructions` vs `@system_prompt`
- No changes to `tools/` namespace MCP servers (those use FastMCP `instructions=` which is different)
