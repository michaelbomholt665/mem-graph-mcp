# 04 — Skills (Code-Based)

## Principle

A code-based skill is a loadable bundle of domain expertise — system-prompt fragments, rule overrides, and tool allowlists — that activates only when a task matches a specific domain. This prevents the full skill surface from inflating every agent's context window on every run.

> **Priority:** Skills are secondary to getting workflows operational. The `skills_content: str` interface threaded through every agent's deps is stable and adequate for now. Code-based skill formalisation follows after the workflow layer is running.

---

## Current State — `skills_content: str`

Every agent dep includes a `skills_content: str` field. At call-time the caller resolves a skill (currently: reads a markdown file) and passes it as a string. The agent injects it under `## Domain Knowledge` in the system prompt.

This interface is the **fixed integration point** that the future skill system must satisfy — the field name and injection point do not change. Only how the string is produced changes.

| Agent | Deps field |
|-------|-----------|
| `audit_agent` / `preloaded_audit_agent` | `skills_content: str` |
| `decision_agent`, `task_agent` | `skills_content: str` |
| `fixer_agent`, `map_agent` | `skills_content: str` |
| `sentry_agent`, `validation_agent` | `skills_content: str` |
| `orchestrator_agent` | `skills_content: str` (threaded to all sub-agents) |
| `router_agent` | `skills_content: str` (appended to prompt tail) |

---

## Proto-Skill: Audit Rule Injection

The closest existing code-skill is the audit rule injection system:

- `agents/audit/rules/` — `DEFAULT_RULES`, `SECURITY_RULES`, `BUG_RULES`, `SMELL_RULES` as typed `AuditRule` lists
- `agents/audit/factory.py` — `build_audit_agent_bundle(rule_set="security")` resolves a named set and wires it into `AuditDependencies.rules`
- `agents/audit/rule_injector_agent.py` — LLM-driven rule selection for unknown languages/frameworks

This is exactly the pattern a skill system follows: named bundles, resolved at call-time, merged into the agent's typed deps.

---

## Proposed Architecture

Skills live inside **existing packages** — no new top-level folder needed:

```
resources/skills/
├── __init__.py          # SkillBundle dataclass, SkillRegistry, load_skill(), skills_match()
├── base.py              # SkillBundle + SkillRegistry
├── python_quality.py    # Python audit rules + prompt fragment
├── security.py          # Cross-language security rule set
└── go_quality.py        # Go naming conventions + rules
```

**Why `resources/skills/`?** Other domain-knowledge objects (personas, prompts, workflows, workflows/reasoning) already live in `resources/`. Skills are the same kind of loadable domain knowledge.

**`SkillBundle` (proposed):**
```python
@dataclass
class SkillBundle:
    name: str
    description: str
    prompt_fragment: str          # → skills_content: str at call-time
    audit_rules: list[AuditRule]  # merged into AuditDependencies.rules
    tool_allowlist: list[str]     # optional future: which tool names this skill unlocks
    languages: list[str]          # triggers: ["python"], ["go"], ["any"]
```

**`load_skill(name)`** — returns a `SkillBundle` from the registry without an LLM hop.
**`skills_match(language, intent)`** — selector analogous to `resources/workflows/selector.py`.

---

## SkillBundle Score Eval (Future)

Once skills are code objects, each `SkillBundle` can be evaluated independently:

```
eval: python_quality skill
  case: known-violation snippet → auditor should find it
  case: clean snippet           → auditor should find nothing
  score: precision + recall of audit findings
```

This gives skills their own performance signal, separate from agent evals (see `08-evals.md`).

---

## Improvement Opportunities

| Issue | Recommendation |
|-------|---------------|
| `skills_content` is a raw string — callers must manually construct it | Add `load_skill(name).prompt_fragment` as the standard call pattern |
| Four audit rule sets live implicitly in `factory.py` | Move to named `SkillBundle` objects in `resources/skills/` — discoverable and composable |
| No match/trigger logic exists — callers must know the skill name | Add `skills_match(language, intent)` returning the best bundle |
| `rule_injector_agent.py` is LLM-driven even for known languages | Reserve for unknown frameworks; use `load_skill()` for deterministic cases |
