# Agents Folder Refactor Plan

## Overview

The `src/mem_graph/agents/` folder currently contains 16 Python files, including agents for various concerns such as auditing, mapping, fixing, validation, documentation, querying, diagramming, triage, decision review, planning, rule injection, chat, orchestration, and routing. To improve organization and maintainability, we propose moving agents into sub-folders based on their primary concern, leaving only the core orchestration files (`orchestrator_graph.py`, `orchestrator_agent.py`) and the router agent (`router_agent.py`) in the root `agents/` folder.

## Current Structure

The current `agents/` folder contains the following files:

- `orchestrator_graph.py` - Main graph for autopilot workflow
- `orchestrator_agent.py` - Batched sub-agent orchestration
- `router_agent.py` - Intent classification and task decomposition
- `sentry_agent.py` - Test architect for red-first validation
- `chat_agent.py` - Memory librarian for graph exploration
- `scribe_agent.py` - Documentation and style enforcer
- `audit_agent.py` - Generic code audit agent
- `diagram_agent.py` - Mermaid diagram generation
- `triage_agent.py` - Violation triage and deduplication
- `decision_agent.py` - Architectural decision review
- `fixer_agent.py` - Code fixing and repair
- `task_agent.py` - Task decomposition
- `rule_injector_agent.py` - Audit rule curation
- `map_agent.py` - Codebase mapping
- `validation_agent.py` - Post-fix quality gate
- `__init__.py` - Package initialization

## Proposed Structure

Move agents into sub-folders based on their primary concern:

```
src/mem_graph/agents/
├── __init__.py
├── orchestrator_graph.py
├── orchestrator_agent.py
├── router_agent.py
├── audit/
│   ├── audit_agent.py
│   └── rule_injector_agent.py
├── map/
│   ├── map_agent.py
│   ├── chat_agent.py
│   └── diagram_agent.py
├── fix/
│   └── fixer_agent.py
├── validate/
│   ├── validation_agent.py
│   └── sentry_agent.py
└── document/
    ├── scribe_agent.py
    ├── triage_agent.py
    ├── decision_agent.py
    └── task_agent.py
```

## Rationale for Grouping

- **audit/**: Agents related to code auditing and rule management (`audit_agent.py` performs audits, `rule_injector_agent.py` curates audit rules).
- **map/**: Agents that build maps, query information, and generate diagrams (`map_agent.py` for codebase mapping, `chat_agent.py` for querying, `diagram_agent.py` for diagramming).
- **fix/**: Agents that perform code fixes and repairs (`fixer_agent.py`).
- **validate/**: Agents involved in validation and testing (`validation_agent.py` for quality gates, `sentry_agent.py` for test planning).
- **document/**: Agents focused on documentation, styling, review, and planning (`scribe_agent.py` for styling, `triage_agent.py` and `decision_agent.py` for review, `task_agent.py` for planning).

Core orchestration and routing agents remain in the root folder as they are foundational and used across the system.

## Migration Steps

1. Create the sub-folder directories: `audit/`, `map/`, `fix/`, `validate/`, `document/`.

2. Move each agent file to its appropriate sub-folder:
   - Move `audit_agent.py` and `rule_injector_agent.py` to `audit/`
   - Move `map_agent.py`, `chat_agent.py`, and `diagram_agent.py` to `map/`
   - Move `fixer_agent.py` to `fix/`
   - Move `validation_agent.py` and `sentry_agent.py` to `validate/`
   - Move `scribe_agent.py`, `triage_agent.py`, `decision_agent.py`, and `task_agent.py` to `document/`

3. Update import statements in dependent files to reflect new paths (e.g., change `from .audit_agent import ...` to `from .audit.audit_agent import ...`).

4. Update the `__init__.py` file to import from the new sub-folders if necessary.

5. Test that all imports and functionality work correctly after the move.

6. Update any documentation or scripts that reference the old file paths.

## Benefits

- **Improved Organization**: Agents are grouped by concern, making it easier to find and maintain related functionality.
- **Reduced Clutter**: The root `agents/` folder will contain only core orchestration files, reducing cognitive load when browsing the directory.
- **Scalability**: New agents can be added to appropriate sub-folders without overcrowding the root folder.
- **Maintainability**: Changes to agents in a specific domain (e.g., auditing) are isolated to their sub-folder.

## Potential Considerations

- Ensure that relative imports within sub-folders are updated if agents import from each other.
- Verify that the package structure does not break any existing tooling or CI/CD pipelines.
- Consider adding `__init__.py` files to sub-folders if they need to expose specific imports.

This refactor will make the agents package more modular and easier to navigate while preserving the existing functionality.
