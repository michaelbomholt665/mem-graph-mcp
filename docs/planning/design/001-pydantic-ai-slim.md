# Design: Pydantic-AI-Slim Integration

**Status:** Design Phase  
**Priority:** High (Foundation for all agents)  
**Date:** 2026-04-13

---

## Overview

Pydantic-AI-Slim is a lightweight agent framework that replaces the monolithic Pydantic-AI dependency. Instead of loading all SDKs (Anthropic, Mistral, Google, etc.), Slim only loads the specified providers, keeping memory footprint and import times lean.

For this 32GB Linux system, we specify `pydantic-ai-slim[openai,google,ag-ui]` to avoid loading unnecessary dependencies while supporting both OpenAI and Google models.

---

## Goals

1. **Reduce Memory Footprint:** Only load required provider SDKs at runtime
2. **Improve Import Times:** Eliminate unnecessary imports during server startup
3. **Maintain Compatibility:** Ensure existing agent code continues to work
4. **Enable Dynamic Model Selection:** Support switching between OpenAI/Google models per-agent

---

## Scope

### In Scope
- Replace `pydantic-ai` with `pydantic-ai-slim[openai,google,ag-ui]` in `pyproject.toml`
- Update agent factory functions (`AgentFactory`, `create_agent_with_model`) to use slim
- Verify all imports in `/src/mem_graph/agents/` work with slim
- Test dynamic model selection (openai vs. google)

### Out of Scope
- Migrating existing agent logic (that's done in Agent Architecture design)
- Changing how agents are instantiated (routing layer applies agent tier selection)
- Support for Anthropic, Mistral, or other unused providers

---

## Architecture

### Current Model Selection

Agents are created via `AgentFactory` in `src/mem_graph/agents/orchestrator_agent.py` with model ties to `ModelTier`:

```python
from ..config import AGENT_MODEL, DEFER_AGENT_MODEL_CHECK

@dataclass
class AgentFactory:
    model_tier: ModelTier = ModelTier.STANDARD
    
    def create(self, agent_name: str) -> Agent:
        model = get_model_for_tier(self.model_tier)
        return Agent(model=model, ...)
```

### New Slim-Based Model Assignment

Update agent factory inside existing subfolders (no new files):

```python
# src/mem_graph/agents/audit/audit_agent.py (updated)
from pydantic_ai import Agent

def create_audit_agent(tier: ModelTier = ModelTier.STANDARD) -> Agent:
    """Create audit agent with tier-based model selection."""
    
    # Use provider prefixes with pydantic-ai-slim
    match tier:
        case ModelTier.QUICK:
            model = "openai:gpt-4o-mini"
        case ModelTier.STANDARD:
            model = "openai:gpt-4o"
        case ModelTier.EXPERT:
            model = "google:gemini-2.0-flash"
        case _:
            model = "openai:gpt-4o"
    
    return Agent(
        model=model,
        system_prompt=AUDIT_SYSTEM_PROMPT,
        tools=[...],  # Existing audit tools
    )

# Same pattern for: fix/, validate/, map/, document/ agents
```

### Dependency Injection

Agents will use lightweight dependency injection to share expensive resources:

```python
from typing import Annotated
from pydantic_ai import Agent, Depends

def get_db_session() -> DBSession:
    """Injected dependency."""
    return DBSession()

async def some_tool(ctx: RunContext[State], db: Annotated[DBSession, Depends(get_db_session)]) -> str:
    # db is automatically injected
    return await db.query(...)
```

---

## Migration Steps

1. **Update `pyproject.toml`:**
   - Change `pydantic-ai>=1.80.0` to `pydantic-ai-slim[openai,google,ag-ui]>=1.80.0`

2. **Update Agent Factory Functions (No new files):**
   - Edit `src/mem_graph/agents/audit/audit_agent.py` → add provider prefix to model
   - Edit `src/mem_graph/agents/fix/fixer_agent.py` → add provider prefix to model
   - Edit `src/mem_graph/agents/validate/sentry_agent.py` → add provider prefix to model
   - Edit `src/mem_graph/agents/map/map_agent.py` → add provider prefix to model
   - Edit `src/mem_graph/agents/document/task_agent.py`, `decision_agent.py`, `triage_agent.py` → add provider prefix to model

3. **Update All Agent Calls:**
   - Wherever agents are instantiated, pass `tier: ModelTier` parameter
   - Agents internally select model based on tier (openai: or google:)

4. **Test Model Switching:**
   - Verify agents work with OpenAI models
   - Verify agents work with Google models
   - Confirm startup time improves

5. **Update Config:**
   - Add `DEFAULT_OPENAI_MODEL` and `DEFAULT_GOOGLE_MODEL` to `config.py`

---

## Implementation Checklist

- [ ] Update `pyproject.toml` with slim dependency
- [ ] Update `audit/audit_agent.py` create function with provider prefixes
- [ ] Update `fix/fixer_agent.py` create function with provider prefixes
- [ ] Update `validate/sentry_agent.py` + `validation_agent.py` with provider prefixes
- [ ] Update `map/map_agent.py` + `chat_agent.py` + `diagram_agent.py` with provider prefixes
- [ ] Update `document/task_agent.py` + `decision_agent.py` + `triage_agent.py` + `scribe_agent.py` with provider prefixes
- [ ] Update `router_agent.py` to pass tier parameter
- [ ] Update `orchestrator_agent.py` to pass tier parameter
- [ ] Test agent instantiation with OpenAI + Google
- [ ] Measure startup time improvement
- [ ] Run full test suite

---

## Success Criteria

1. Agents instantiate with `pydantic-ai-slim` without errors
2. Model switching (OpenAI ↔ Google) works per-tier
3. Startup time is measurably faster than full `pydantic-ai`
4. All existing agent tests pass
5. Memory footprint is reduced (measured via `psutil` or similar)

---

## Notes

- Slim is the recommended path forward for Pydantic-AI; full `pydantic-ai` is being deprecated in favor of the modular slim approach
- Provider prefixes (`openai:`, `google:`) are mandatory with slim
- No changes to agent *logic* required—only model instantiation
