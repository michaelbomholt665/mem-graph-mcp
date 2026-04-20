# Workflows README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `models.py` | 197 | Pydantic models (WorkflowResource, WorkflowProfile, ReasoningPolicy, etc.) | pydantic |
| `profiles.py` | 194 | SMALL/MEDIUM/LARGE profile definitions | models |
| `reasoning.py` | 174 | Reasoning policy definitions + prompt rendering | models |
| `task_types.py` | 157 | Task type → profile size mapping | models |
| `workflow_definitions.py` | 938 | 24 WorkflowResource definitions (Group A) | models |
| `registry.py` | 269 | Workflow registry + lookup functions | models, workflow_definitions |
| `selector.py` | 207 | Workflow/profile/reasoning selector | models, profiles, reasoning, registry, task_types |
| `visualization.py` | 78 | Mermaid diagram generation from registry | models, registry |
| `__init__.py` | 65 | Re-exports public API | All modules |

## Dependency Analysis

### Data definition layer (4 files, all import only from models.py)
- `profiles.py` — 3 profile instances + lookup map
- `reasoning.py` — 4 policy instances + prompt rendering helpers
- `task_types.py` — task type → profile size map + category groupings
- `workflow_definitions.py` — 24 workflow resource instances (938 lines)

### Registry layer (1 file)
- `registry.py` — imports from `models` and `workflow_definitions`; defines 3 built-in workflows + combines with Group A

### Selection/rendering layer (2 files)
- `selector.py` — imports from models, profiles, reasoning, registry, task_types; deterministic selection logic
- `visualization.py` — imports from models, registry; renders Mermaid diagrams

### Size concern
`workflow_definitions.py` at 938 lines is the largest file in the package. It defines 24 WorkflowResource objects in a single module. This is the primary refactor target.

## Refactor Suggestion

### Primary: Split workflow_definitions.py by priority group
The 24 workflows are already organized by priority (1–11). Split them into separate definition modules:

- **definitions/feature_implementation.py**: FEATURE_IMPLEMENTATION (P1)
- **definitions/refactor.py**: REFACTOR (P2)
- **definitions/research.py**: RESEARCH (P3)
- **definitions/security.py**: SECURITY_HARDENING (P4)
- **definitions/performance.py**: PERFORMANCE_PROFILING (P5)
- **definitions/authoring.py**: ADR_AUTHORING, FEATURE_DESIGN, SCHEMA_DESIGN, API_CONTRACT_DESIGN, DESIGN_DOCS, RUNBOOK_AUTHORING, COMMAND_DESIGN, ERROR_LOGGING_DESIGN (P6, all design/authoring)
- **definitions/dependency_audit.py**: DEPENDENCY_AUDIT, CI_SETUP (P7)
- **definitions/documentation.py**: DOCS_GENERATION, CHANGELOG_AUTHORING, ONBOARDING_DOCS (P8)
- **definitions/release.py**: RELEASE_PREPARATION, DEPLOYMENT_VALIDATION (P9)
- **definitions/utility.py**: UTILITY_EXTRACTION (P10)
- **definitions/planning.py**: IMPLEMENTATION_PLANNING, PROJECT_SCAFFOLD (P11)

Each file exports a `list[WorkflowResource]`. `registry.py` imports and concatenates them instead of importing a single `GROUP_A_WORKFLOWS`.

This keeps each definition file under 200 lines and makes it easy to find which file owns a specific workflow.

### Secondary: Group selection and rendering
- **selection/**: `selector.py`, `task_types.py`

`selector.py` imports from `task_types.py` for the base profile selection. They form a coherent "given a task, pick the right profile/workflow" concern. `visualization.py` is rendering, not selection — it stays in root.

### Files staying in root
`__init__.py`, `models.py`, `profiles.py`, `reasoning.py`, `registry.py`, `visualization.py`

These are either foundational types (`models.py`), small data files (`profiles.py`, `reasoning.py`), or the central registry that ties definitions together.

### Not recommended
- Moving `profiles.py` or `reasoning.py` into a `definitions/` sub-package — they are not workflow definitions, they are reusable policy/profile data used by the selector
- Putting `visualization.py` in `selection/` — it's a rendering concern, not a selection concern
