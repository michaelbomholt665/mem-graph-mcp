# Design: Pydantic-AI-Skills Integration (Python-Native Skills)

**Status:** Design Phase  
**Priority:** High (Replaces ad-hoc tools)  
**Date:** 2026-04-13

---

## Overview

Pydantic-AI-Skills provides a structured way to package tools as "skills"—reusable, typed capabilities organized in directories with documentation, scripts, and data. Instead of scattered Python files in `/tools/`, skills are organized as importable modules with:

1. **Manual (description):** What the skill does
2. **Execution (scripts):** How to use it (functions)
3. **Data (references):** Supporting docs and examples

This replaces the current file-based tool approach with type-safe, composable modules.

---

## Goals

1. **Eliminate Markdown Skill Files:** Replace `.md` skill definitions with Python objects
2. **Enable Type Validation:** Pydantic validates inputs/outputs at runtime
3. **Simplify Tool Discovery:** Agents see high-level skill list, load details on-demand
4. **Improve Testability:** Skills are testable as regular Python modules
5. **Support Dynamic Assets:** References can be live data from graph, not static files

---

## Scope

### In Scope
- Wrap existing tools in `tools/` subdirectories as Skill objects
- Create `Skill` wrapper classes for each domain (memory, work, agents, filesystem)
- Add Pydantic validation to tool inputs/outputs
- Add `@skill.script()` decorators to tool functions
- Create skill discovery layer (agents see skills, not raw tools)

### Out of Scope
- Creating new tools or agents (skills wrap existing)
- Changing underlying tool logic
- Restructuring tools/ directory (keep current layout)

---

## Architecture (No New Agents - Wrapping Existing Tools)

### 1. Skill Definition

Current tool structure is already organized well. Skills wrap existing tools:

```
tools/
  ├── memory/     → memory_skill
  ├── work/       → work_skill  
  ├── agents/     → agents_skill (calls agents, wrapped as skill)
  └── filesystem/ → filesystem_skill
```

No new agents or tool files—skills are wrappers around existing `/tools/` functions.

```python
# src/mem_graph/skills/memory.py (wraps tools/memory/memory.py)

from pydantic_ai_skills import Skill, script

skill = Skill(
    name="memory",
    description="Store and retrieve facts from persistent memory",
    instructions="""Use memory_store() to save, memory_recall() to find."""
)

@skill.script()
async def memory_store(content: str, tags: list[str] | None = None) -> dict:
    """Store fact (wraps existing tools/memory/memory.py::memory_store)."""
    # Calls existing tool, adds Pydantic validation
    return await tools.memory.memory_store(content, tags)
```
```

### 2. Skill Scripts (Functions)

```python
# src/mem_graph/skills/memory.py

from pydantic_ai_skills import Skill, script
from pydantic import BaseModel, Field
import httpx

class FactNode(BaseModel):
    """A single fact stored in memory."""
    fact_id: str = Field(description="Unique ID (auto-generated)")
    content: str = Field(description="The fact text")
    project_id: str = Field(description="Project context")
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.9)

class RecallResult(BaseModel):
    """Results from memory recall."""
    facts: list[FactNode] = Field(default_factory=list)
    total: int = 0
    query: str = ""

skill = MemorySkill()

@skill.script()
async def memory_store(
    content: str,
    project_id: str,
    tags: list[str] | None = None,
    confidence: float = 0.9,
) -> FactNode:
    """
    Store a new fact in the knowledge graph.
    
    Args:
        content: The fact to store (1-500 words)
        project_id: Project this fact belongs to
        tags: Optional labels ("pattern", "decision", "bugfix", etc.)
        confidence: How confident you are (0-1)
    
    Returns:
        The stored FactNode with assigned fact_id
    
    Examples:
        - content="User prefers early returns in Go"
          tags=["style", "go"]
        - content="DuckDB performance bottleneck in parsing module"
          tags=["performance", "core"]
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:9100/memory_store",
            json={
                "content": content,
                "project_id": project_id,
                "tags": tags or [],
                "confidence": confidence,
            }
        )
        response.raise_for_status()
        return FactNode(**response.json())

@skill.script()
async def memory_recall(
    query: str,
    project_id: str,
    limit: int = 5,
) -> RecallResult:
    """
    Recall facts related to a query.
    
    Uses semantic search (embeddings) + keyword search (BM25).
    
    Args:
        query: What you want to find (e.g., "early returns Go style")
        project_id: Project context
        limit: Max results (1-50)
    
    Returns:
        RecallResult with matching facts
    
    Examples:
        - query="refactoring patterns"
          → returns facts tagged with "pattern"
        - query="performance issues"
          → returns facts tagged with "performance"
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:9100/memory_recall",
            json={
                "query": query,
                "project_id": project_id,
                "limit": limit,
            }
        )
        response.raise_for_status()
        result = response.json()
        return RecallResult(
            facts=[FactNode(**f) for f in result["facts"]],
            total=result["total"],
            query=query,
        )

@skill.script()
async def memory_annotate(
    fact_id: str,
    tags: list[str] | None = None,
    confidence: float | None = None,
) -> FactNode:
    """
    Update metadata on an existing fact.
    
    Args:
        fact_id: ID of fact to update
        tags: New tags (replaces old tags)
        confidence: New confidence value
    
    Returns:
        Updated FactNode
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"http://localhost:9100/memory_store/{fact_id}",
            json={
                "tags": tags,
                "confidence": confidence,
            }
        )
        response.raise_for_status()
        return FactNode(**response.json())

# Skill references (live data from graph)
skill.add_reference(
    "memory-best-practices",
    description="Guidelines for effective memory usage",
    fetch_func=lambda: {
        "principles": [
            "1. Check before storing: Use memory_recall to avoid duplicates",
            "2. Tag everything: Use consistent tags for findability",
            "3. Confidence matters: Set high confidence only for verified facts",
            "4. Audit trail: Use note_write for decision justifications",
        ],
        "common_tags": ["pattern", "performance", "style", "bugfix", "decision"],
    }
)
```

### 3. Skill Groups (Domains)

Organize related skills:

```python
# src/mem_graph/skills/__init__.py

from pydantic_ai_skills import SkillsToolset
from .memory import skill as memory_skill
from .work import skill as work_skill
from .agents import skill as agents_skill
from .filesystem import skill as filesystem_skill

class SkillRegistry:
    """Registry of all available skills."""
    
    # Domain groupings
    MEMORY_SKILLS = SkillsToolset(skills=[memory_skill])
    WORK_SKILLS = SkillsToolset(skills=[work_skill])
    AGENT_SKILLS = SkillsToolset(skills=[agents_skill])
    FILESYSTEM_SKILLS = SkillsToolset(skills=[filesystem_skill])
    
    # All skills for CodeMode discovery
    ALL_SKILLS = SkillsToolset(skills=[
        memory_skill,
        work_skill,
        agents_skill,
        filesystem_skill,
    ])
```

### 4. Agent Integration

Agents declare which skills they use:

```python
# src/mem_graph/agents/audit_agent.py

from pydantic_ai import Agent
from ..skills import SkillRegistry

async def create_audit_agent(tier: ModelTier) -> Agent:
    """Create audit agent with memory + agents skills."""
    
    return Agent(
        model=get_model_for_tier(tier),
        tools=SkillRegistry.MEMORY_SKILLS.all_tools() + \
              SkillRegistry.AGENT_SKILLS.all_tools(),
        system_prompt="""
You are an audit agent. Your role is to analyze code for issues, 
patterns, and opportunities.

Available skills:
- memory: Store findings, recall patterns
- agents: Trigger other agents for sub-tasks
        """
    )

async def create_fix_agent(tier: ModelTier) -> Agent:
    """Create fix agent with filesystem + work + memory skills."""
    
    return Agent(
        model=get_model_for_tier(tier),
        tools=SkillRegistry.FILESYSTEM_SKILLS.all_tools() + \
              SkillRegistry.WORK_SKILLS.all_tools() + \
              SkillRegistry.MEMORY_SKILLS.all_tools(),
        system_prompt="""
You are a fix agent. Your role is to propose and apply code changes.

Available skills:
- filesystem: Read/write/edit files
- work: Track tasks, decisions, violations
- memory: Store patterns, recall past fixes
        """
    )
```

### 5. FastMCP Server Integration

Skills are mounted as tools on the FastMCP server:

```python
# src/mem_graph/server.py

from .skills import SkillRegistry

mcp = FastMCP(name="memory")

# Mount skill toolsets under namespace
for skill in SkillRegistry.ALL_SKILLS.skills:
    for tool in skill.scripts:
        mcp.tool(
            name=f"{skill.name}_{tool.name}",
            description=tool.description,
        )(tool.func)

# Lazy namespace: expose skills on-demand
@mcp.lazy_namespace("memory")
async def memory_namespace() -> dict[str, Any]:
    """Expose memory skill tools only when agent activates this namespace."""
    return {
        tool.name: tool.func
        for skill in [SkillRegistry.MEMORY_SKILLS]
        for tool in skill.all_tools()
    }
```

### 6. CodeMode Discovery

In CodeMode, agents use a skill search tool instead of seeing all tools:

```python
# Pseudo-code for CodeMode

async def search_skills(query: str) -> list[SkillDescription]:
    """
    BM25 search over skill names + descriptions.
    
    Returns high-level skill info (not full tool schemas).
    
    Example:
      search_skills("memory") → 
        [{
          "skill": "memory",
          "description": "Store and retrieve persistent facts",
          "functions": ["memory_store", "memory_recall", "memory_annotate"],
        }]
    """
    pass

async def inspect_skill(skill_name: str) -> SkillDetail:
    """
    Get full details for a skill (docstrings, parameters, examples).
    
    Called when agent wants to use a skill.
    """
    pass
```

---

## Benefits Over Current File-Based Approach

| Aspect | File-Based | Skills |
|--------|-----------|--------|
| **Tool Discovery** | All tools visible (bloat) | Skills hidden until needed |
| **Type Safety** | Loose dict/Optional types | Full Pydantic validation |
| **Documentation** | Scattered `.md` files | Embedded in Python docstrings |
| **Testing** | Test tools + extra harness | Test functions directly |
| **Updates** | Restart server | Reload skill module |
| **IDE Support** | None | Full autocomplete + type hints |

---

## Migration Path

1. **Phase 1:** Create `Skill` wrapper classes for each domain (memory, work, agents, filesystem)
2. **Phase 2:** Convert tool functions to `@skill.script()` decorated functions
3. **Phase 3:** Add skill references (live data fetchers)
4. **Phase 4:** Integrate with agent factory (agents declare skills they use)
5. **Phase 5:** Update FastMCP server to mount skills as tools
6. **Phase 6:** Cleanup—remove old tool files as skills take over

---

## Implementation Checklist

- [ ] Create `Skill` classes for each domain (memory, work, agents, filesystem)
- [ ] Convert existing tool functions to `@skill.script()` format
- [ ] Implement skill references (live data from graph)
- [ ] Create `SkillRegistry` with domain groupings
- [ ] Update agents to use `SkillRegistry` instead of raw tools
- [ ] Mount skills on FastMCP server
- [ ] Implement skill search + inspect for CodeMode
- [ ] Test agent behavior with skills
- [ ] Test CodeMode discovery with skills

---

## Success Criteria

1. All tools are organized as skills with clear documentation
2. Skills are validated via Pydantic
3. Agents can selectively load skills
4. No regression in agent functionality
5. IDE autocomplete works for skill functions

---

## Dependencies

- `pydantic-ai-skills>=0.7.0` (already in `pyproject.toml`)
- Pydantic for validation
- Existing tool implementations (wrapped by skills)

---

## Notes

- Skills wrap existing tools from `tools/` subdirectories—no new agents or tool files
- Skills are thin wrappers that add Pydantic validation and documentation
- Skills enable "progressive disclosure"—agents don't see all tools until they need them
- This is a refactor of tool discovery, not tool structure
