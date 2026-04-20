# Code Review: `src/mem_graph/resources/`

**Reviewed:** 2026-04-14
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Scope:** `architecture.py`, `coding_standards.py`, `node_styles.json`, `personas.py`, `prompts.py`

---

## Summary

The resources package is a read-only configuration layer — no database access, no I/O. It holds prompt templates, persona definitions, coding standards strings, and architecture guardrails. (Note: Trait range and LLM parameter validation are now covered in 016-resources-review.md). The code is essentially data; there is little control flow to go wrong. Two issues are noted: a missing `__init__.py` (which could cause import confusion) and an injection risk in `get_sub_agent_instructions`.

---

## Critical Issues

_None._

---

## Suggestions

| # | File | Line | Suggestion | Category |
|---|------|------|------------|----------|
| 1 | `prompts.py` | ~9 | **`get_sub_agent_instructions` injects `specific_task` directly into a prompt string without sanitization.** The `specific_task` parameter comes from the MCP tool caller (`prompt_sub_agent_spinup`) which accepts `task` from the LLM. A malicious task string could contain `--- SUB-AGENT SPIN-UP:` header sequences that confuse downstream prompt parsers, or inject additional instructions. Wrap `specific_task` in a delimited block that is not syntactically meaningful to the persona prompt format. | Security |
| 2 | `resources/` | top | **Missing `__init__.py`.** The directory lacks an `__init__.py` (the `__pycache__` exists, meaning Python treats it as a namespace package). This works in Python 3.3+ but is inconsistent with the rest of the package which uses explicit `__init__.py` files. Add one to make the package boundary explicit. | Maintainability |
| 3 | `prompts.py` | ~60 | **`PROMPT_REGISTRY` is a module-level dict of multi-line strings.** If a prompt references a tool name that has been renamed (e.g., `project_list()` which appears in `SYNC_CONTEXT_PROMPT` but may not actually exist as a tool), the error only surfaces at runtime when the client LLM calls the tool. Consider validating that all tool names referenced in prompts exist at startup. | Maintainability |
| 4 | `coding_standards.py` | ~15 | **Python standard version is hardcoded as `v3.13+` and Go as `v1.25.4`.** These constants will silently become outdated as the project moves forward. Source from `pyproject.toml` / `go.mod` or add a comment with the date last reviewed. | Maintainability |

---

## What Looks Good

- **`Persona.get_system_instructions()`** — Clean rendering that embeds OCEAN traits into the system prompt. Trait-based prompt specialisation is a well-documented LLM steering technique.
- **Per-persona `LLMParams`** — Deliberately low `temperature=0.2` for `AUDITOR_PERSONA` and very low `temperature=0.1` for `RULE_INJECTOR_PERSONA` reflects correct reasoning that deterministic, precise tasks need coolest sampling.
- **`PERSONA_REGISTRY`** — Central dict keyed by short name (`"auditor"`, `"architect"`, etc.) enables `sub_agent_spinup` prompt to be language-agnostic.
- **`MANIFEST_GUARD_RULE`** — Excellent: requiring agents to read `pyproject.toml`/`go.mod` before proposing dependency changes prevents hallucinated imports.
- **Coding standards as injected strings** — Keeps language standards in one place rather than scattered across agent system prompts.

---

## Verdict

**Approve with comments** — No critical issues. The prompt-injection concern in `get_sub_agent_instructions` and the missing package `__init__.py` are the most actionable items.
