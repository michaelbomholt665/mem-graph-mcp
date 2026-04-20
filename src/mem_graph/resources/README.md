# Resources README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `architecture.py` | 79 | Architectural guardrail strings for agent prompts | None |
| `coding_standards.py` | 122 | Language-specific coding standard strings | None |
| `personas.py` | 437 | Agent persona definitions (Big Five traits, LLM params) | None |
| `prompts.py` | 365 | Workflow stage prompts, reasoning templates, PROMPT_REGISTRY | personas (for `get_sub_agent_instructions`) |
| `prompts_evals.py` | 54 | Eval-specific prompt variants | prompts (imports PROMPT_REGISTRY) |
| `node_styles.json` | — | Graph node styling data | None |
| `workflows/` | — | Workflow resource definitions (see workflows/README.md) | — |

## Dependency Analysis

### Coupled chain: personas → prompts → prompts_evals
- `prompts.py` imports `PERSONA_REGISTRY` from `personas.py` for `get_sub_agent_instructions()`
- `prompts_evals.py` imports `PROMPT_REGISTRY` from `prompts.py` for eval variant mirroring
- These three files form a dependency chain that should move together

### Standalone string resources
- `architecture.py` — pure string constants, no imports from other resource files
- `coding_standards.py` — pure string constants plus a small lookup function, no imports from other resource files
- `node_styles.json` — static data file

## Refactor Suggestion

### Primary: Move coupled prompt files into sub-package
- **prompts/**: `personas.py`, `prompts.py`, `prompts_evals.py`

These three form a coherent dependency chain. Grouping them:
- Keeps persona definitions next to the prompt templates that consume them
- Allows `prompts/__init__.py` to re-export the public API (`PROMPT_REGISTRY`, `PERSONA_REGISTRY`, `get_sub_agent_instructions`, `get_eval_prompt`)
- Separates agent-facing prompt concerns from the architectural/standards guardrails that stay in root

### Files staying in root
`__init__.py`, `architecture.py`, `coding_standards.py`, `node_styles.json`

`architecture.py` and `coding_standards.py` are standalone injectable strings with no inter-file dependencies. They are consumed by different injection points (system prompt guardrails vs scribe agent instructions) and don't share a concern with the prompt registry.

### Not recommended
- Creating a `personas/` directory for a single file — personas.py has no reason to be isolated
- Creating a `styles/` directory for `node_styles.json` alone — one static file doesn't justify a package
- Moving `architecture.py` into prompts/ — it's a guardrail, not a prompt template, and has no dependency on the prompt registry
