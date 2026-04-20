# Task 025 (v3): Improve Tool/Agent/Prompt/Skill Visibility

## Changelog
| Version | What changed |
|---|---|
| v1 | Original plan — proposed building all discovery tools from scratch |
| v2 | Replaced most custom code with native FastMCP transforms; added Pydantic AI notes |
| v3 | Replaced `list_skills` with intent-based dispatch model (category + task_type); skill registry scaffolded but empty pending sub-agent workflow completion |
| v3.1 | Added tool description verbosity as an explicit problem; added description audit to implementation plan |

---

## Problem Statement

There are two distinct problems, both waste context:

### Problem 1 — Discovery Gap
Discovering the full capability surface requires multiple tool calls or codebase spelunking. `list_agents` only covers one category, is hardcoded, and leaks no information about what kind of work agents can do. Prompts and Resources are invisible unless you read source code directly.

### Problem 2 — Description Verbosity (observed in practice)
A search for the word "list" returned 14 of 63 tools — and that output alone was a 100-line wall of text. That means a full `list_tools` response for all 63 tools would be approximately **450 lines** of text just to read what the server can do. This is too expensive for any agent to call routinely.

The root cause: tool docstrings are written for human readers browsing source code, not for LLMs consuming them at runtime. Multi-sentence descriptions, usage notes, parameter explanations, and warnings are all packed into the description field that gets sent to the LLM on every tool call.

**Observed example** — `memory_manage` description as it appears to an agent today:
```
Manage stored memories: expire outdated facts or list and browse what's saved.

Use action='expire' with a memory_id to soft-delete a fact that is no
longer accurate. Use action='list' to browse active memories, optionally
filtered by scope or project. Returns the operation result or memory list.

Expiring a memory is a destructive operation — the client will be asked
to confirm before the change is committed.
```
That is 6 lines for one tool. Multiplied across 63 tools = ~378 lines before any tool is called.

**Target:** one tight sentence per tool. Detail lives in parameter descriptions and a separate `help` resource, not in the top-level docstring.

---

## Architecture: What Parent Agents Know vs. What Sub-Agents Know

The key design principle introduced in v3: **skills are not part of the public API surface.**

```
Parent agent
  knows → categories, task types
  does  → spawn_subagent(task=..., category="database", task_type="sql_security")

Sub-agent
  knows → skills (internal)
  does  → resolve_skill(category, task_type) → pick best → execute
```

Parent agents never see skill names or skill logic. They speak in *intent* (category + task type). Sub-agents resolve that intent to a concrete skill internally. This means adding new skills never requires updating any parent agent — they just become available to the resolver automatically.

---

## Part 1: FastMCP Native Transforms (Zero Custom Code)

FastMCP v3 ships transforms that handle prompt and resource discovery out of the box. Wire these first.

```python
# src/mem_graph/app/helpers.py  # transforms under src/mem_graph/resources/transform/

from fastmcp import FastMCP
from fastmcp.server.transforms import ResourcesAsTools, PromptsAsTools
from fastmcp.server.transforms.search import BM25SearchTransform

mcp = FastMCP(
    "MemGraph",
    instructions=(
        "Start with `system_inspect` for a full orientation, or `search_tools` to find "
        "capabilities by natural language. Use `list_task_types` to see what categories "
        "and task types are available for spawning sub-agents. Use `list_agents` for "
        "registered sub-agents. Use `list_resources` and `list_prompts` to browse "
        "data sources and prompt templates."
    ),
    transforms=[
        ResourcesAsTools(mcp),       # adds list_resources + read_resource
        PromptsAsTools(mcp),         # adds list_prompts + get_prompt
        BM25SearchTransform(
            max_results=8,
            always_visible=[         # always show these without searching
                "system_inspect",
                "list_agents",
                "list_task_types",
            ],
        ),
    ],
)
```

---

## Part 2: Agent Registry (`src/mem_graph/app/registry.py` or `src/mem_graph/agents/`)

Replaces the hardcoded `list_agents`. Each agent registers itself at import time.

```python
# src/mem_graph/app/registry.py  # or src/mem_graph/agents/registry.py

from dataclasses import dataclass, field

@dataclass
class AgentEntry:
    name: str
    description: str
    categories: list[str] = field(default_factory=list)  # e.g. ["database", "code"]
    task_types: list[str] = field(default_factory=list)  # e.g. ["sql_security", "refactoring"]

_AGENTS: dict[str, AgentEntry] = {}

def register_agent(entry: AgentEntry) -> None:
    _AGENTS[entry.name] = entry

def all_agents() -> list[AgentEntry]:
    return sorted(_AGENTS.values(), key=lambda a: a.name)
```

---

## Part 3: Skill Registry (`src/mem_graph/providers/skills/registry.py`)

### Current state: 0 skills registered

The registry infrastructure is built now so the dispatch model is in place. Skills will be added after the sub-agent workflow is designed (coding, audits, debugging pipeline). Until then, `_SKILLS` is empty and `list_task_types` returns an empty map — which is honest and correct.

```python
# src/mem_graph/providers/skills/registry.py

from dataclasses import dataclass, field

@dataclass
class SkillEntry:
    name: str
    category: str          # e.g. "database"
    task_types: list[str]  # e.g. ["sql_security", "concurrency"]
    description: str = ""
    static_priority: int = 0   # manual tuning knob
    eval_score: float = 1.0    # updated by eval runs; defaults to neutral

    @property
    def dispatch_score(self) -> float:
        return self.static_priority * self.eval_score

# Empty until sub-agent workflow is designed
_SKILLS: list[SkillEntry] = []

def register_skill(skill: SkillEntry) -> None:
    _SKILLS.append(skill)

def all_skills() -> list[SkillEntry]:
    return list(_SKILLS)

def resolve_skill(category: str, task_type: str) -> SkillEntry | None:
    """
    Find the best skill for a given category + task_type combination.
    Filters by both fields, ranks by dispatch_score descending.
    Returns None if no skill matches — caller should handle gracefully.
    """
    candidates = [
        s for s in _SKILLS
        if s.category == category and task_type in s.task_types
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.dispatch_score)

def task_type_map() -> dict[str, list[str]]:
    """
    Returns the public-facing capability map: category → [task_types].
    This is what parent agents see. Skill names never appear here.
    """
    result: dict[str, set[str]] = {}
    for skill in _SKILLS:
        result.setdefault(skill.category, set()).update(skill.task_types)
    return {cat: sorted(types) for cat, types in sorted(result.items())}
```

### Adding a skill later (example — for reference when workflow is ready)

```python
# Example: what registering a future skill will look like
register_skill(SkillEntry(
    name="pg_security_audit",
    category="database",
    task_types=["sql_security", "audit"],
    description="Audits PostgreSQL queries for injection risks and privilege escalation.",
    static_priority=10,
))
```

---

## Part 4: Discovery Tools (`src/mem_graph/tools/`)

### `list_task_types` — public tool for parent agents

```python
@mcp.tool(tags={"discovery"})
def list_task_types() -> dict:
    """
    Returns all available task categories and their task types.
    Use this to know what category + task_type to pass when spawning a sub-agent.
    Skills are resolved internally — you never need to name them directly.

    Currently returns an empty map (no skills registered yet).
    """
    return task_type_map()  # {} until skills are added
```

### `list_agents` — driven by registry, not hardcoded

```python
@mcp.tool(tags={"discovery"})
def list_agents() -> list[dict]:
    """Lists all registered sub-agents with their categories and task types."""
    return [
        {
            "name": a.name,
            "description": a.description,
            "categories": a.categories,
            "task_types": a.task_types,
        }
        for a in all_agents()
    ]
```

### `system_inspect` — unified orientation in one call

```python
@mcp.tool(tags={"discovery"})
async def system_inspect(ctx: Context) -> dict:
    """
    High-level snapshot of everything the server can do.
    Returns counts and examples for: tools, agents, prompts, resources, task types.
    Call this first when you need a quick orientation.

    Note: skills count is 0 — skill workflow is under construction.
    """
    tools     = await ctx.fastmcp.list_tools()
    prompts   = await ctx.fastmcp.list_prompts()
    resources = await ctx.fastmcp.list_resources()
    agents    = all_agents()
    ttmap     = task_type_map()  # {} for now

    def summarise(items, name_fn):
        names = [name_fn(i) for i in items]
        return {"count": len(names), "examples": names[:5]}

    return {
        "tools":      summarise(tools,     lambda t: t.name),
        "prompts":    summarise(prompts,   lambda p: p.name),
        "resources":  summarise(resources, lambda r: r.uri),
        "agents":     summarise(agents,    lambda a: a.name),
        "task_types": {
            "status": "pending — skill workflow under construction",
            "categories": ttmap,  # {} until skills are registered
        },
    }
```

---

## Part 5: Eval-Driven Skill Scoring (`src/mem_graph/evals`)

Once skills are registered, Pydantic Evals can run offline against each skill with representative tasks and write scores back into the registry. This makes the dispatch system self-improving without hardcoding preferences.

```python
# Future: after sub-agent workflow is complete
# Run evals per skill → update eval_score → resolver automatically deprioritizes weak skills

skill = resolve_skill("database", "sql_security")
skill.eval_score = 0.73  # written back from eval run
# dispatch_score = static_priority * 0.73 — now ranks below a higher-scoring alternative
```

The scoring is two-layered:
- **Static priority** (`static_priority`) — manual tuning, set at registration time
- **Eval score** (`eval_score`) — learned weight from offline eval runs, defaults to 1.0 (neutral)

---

## Implementation Plan

| Step | What | Where | Status |
|---|---|---|---|
|[x]| Wire `ResourcesAsTools` + `PromptsAsTools` + `BM25SearchTransform` | `src/mem_graph/app/helpers.py` | Do now |
|[x]| Update `FastMCP(instructions=...)` string | `src/mem_graph/app/helpers.py` | Do now |
|[x]| Create `app/registry.py` with `AgentEntry` | `src/mem_graph/app/registry.py` or `src/mem_graph/agents/` | Do now |
|[x]| Refactor `list_agents` to use registry | `src/mem_graph/tools/` | Do now |
|[x]| Create skills registry with empty `_SKILLS` + full resolver logic | `src/mem_graph/providers/skills/skills.py` | Do now (scaffold only) |
| [x]| Add `list_task_types` + `system_inspect` tools | `src/mem_graph/tools/` | Do now |
| **7** | **Audit and rewrite all 63 tool docstrings to one tight sentence each** | `src/mem_graph/tools/` | Do now — high impact |
| 8 | Design sub-agent workflow (coding, audit, debug pipeline) | separate task | Soon |
| 9 | Register first real skills | `app/skills.py` | After step 8 |
| 10 | Wire Pydantic Evals → `eval_score` feedback loop | eval harness | After step 9 |

### Step 7 in detail — Docstring Audit Rules

Every tool description must pass this checklist before it ships:

- **One sentence max** in the top-level docstring. If you can't say it in one sentence, the tool is doing too much.
- **No usage examples** in the docstring. Those go in a `help://tools/{name}` resource or in parameter descriptions.
- **No "Returns X" prose** in the docstring. Return shape is self-documenting via the return type annotation.
- **No warnings or caveats** in the docstring. Destructive operations get a `tags={"destructive"}` tag and a parameter-level note.
- **Parameter descriptions carry the detail.** FastMCP passes per-parameter descriptions to the LLM separately — use them.

Before/after example:

```python
# BEFORE (6 lines, 67 words)
def memory_manage(...):
    """
    Manage stored memories: expire outdated facts or list and browse what's saved.

    Use action='expire' with a memory_id to soft-delete a fact that is no
    longer accurate. Use action='list' to browse active memories, optionally
    filtered by scope or project. Returns the operation result or memory list.

    Expiring a memory is a destructive operation — the client will be asked
    to confirm before the change is committed.
    """

# AFTER (1 line, 9 words)
def memory_manage(...):
    """Expire or list stored memories by scope or project."""
```

Target: average description under 12 words. At 63 tools × 12 words, the full tool listing fits comfortably within a single reasonable context chunk instead of 450 lines.

---

## Success Criteria

- A fresh agent session needs **at most 2 tool calls** to be fully oriented: `system_inspect` then `search_tools`.
- Parent agents **never see skill names** — only categories and task types.
- `list_task_types` returns `{}` honestly until skills are registered (no fake data).
- `list_agents` is registry-driven — adding an agent requires no edits to the tool.
- `resolve_skill(category, task_type)` is in place and tested with 0 skills returning `None` gracefully.
- Eval score feedback loop is designed (even if not yet running).
- No capability category requires codebase investigation to discover.
- **Full `list_tools` output for all 63 tools fits in under 80 lines.** (Currently ~450 lines for 14 tools shown.)
