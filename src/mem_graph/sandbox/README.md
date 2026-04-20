# Sandbox README

## Current Structure

| File | Lines | Role | Key Dependencies |
|------|-------|------|------------------|
| `config.py` | 94 | Environment-backed settings (SandboxSettings) | None |
| `models.py` | 93 | Pydantic models for sessions, execution, policies | pydantic |
| `errors.py` | 31 | Typed exception hierarchy | None |
| `manager.py` | 224 | Session lifecycle orchestrator | config, errors, models, podman, snapshots |
| `provider.py` | 132 | FastMCP CodeMode integration | errors, manager, models, fastmcp |
| `compose.py` | 64 | Podman compose argument construction | errors, models |
| `podman.py` | 193 | Podman CLI adapter (start/exec/stop/inspect) | compose, config, errors, models |
| `cleanup.py` | 24 | Periodic stale session cleanup task | manager |
| `snapshots.py` | 213 | Repo snapshot, workspace init, and merge-back | errors, models |

## Dependency Analysis

### Data Layer (no internal deps)
`config.py`, `models.py`, `errors.py` — foundational types and settings imported by everything else.

### Container Boundary (2 files, tightly coupled)
`compose.py` ← `podman.py`
- `podman.py` calls `compose.py` functions to build CLI arguments
- Both operate at the subprocess boundary — they never touch the filesystem directly

### Filesystem Operations (1 file)
`snapshots.py` — handles repo copying, workspace initialization, merge-back
- Pure filesystem operations with no subprocess calls
- Imported only by `manager.py`

### Lifecycle (2 files)
`manager.py` — the central orchestrator, imports from nearly every other module
`provider.py` — FastMCP integration that wraps the manager for CodeMode
- `provider.py` depends on `manager.py`, not the other way around

### Maintenance
`cleanup.py` — tiny async task that calls `manager.cleanup_stale()` periodically

## Refactor Suggestion

### Extract data layer into sub-package
- **models/**: `models.py`, `errors.py`, `config.py`

All three are pure data/config definitions with no behavioral dependencies. Grouping them separates the "what" from the "how" and mirrors the pattern used in `sandbox/`'s public `__init__.py` re-exports.

### Extract container adapter into sub-package
- **containers/**: `compose.py`, `podman.py`

These form the subprocess boundary — all Podman CLI interaction is contained here. `podman.py` is the adapter, `compose.py` is its argument builder. Keeping them together makes it easy to swap container backends or add Docker support.

### Extract filesystem operations
- **filesystem/**: `snapshots.py`

`snapshots.py` is 213 lines of repo-copy, workspace-init, and merge-back logic. It's a distinct concern from container management. As more filesystem operations are added (e.g., artifact archival, diff generation), they'd go here.

### Files staying in root
`__init__.py`, `manager.py`, `provider.py`, `cleanup.py`

- `manager.py` is the top-level orchestrator that ties everything together — it should stay visible at the package root
- `provider.py` is a FastMCP integration adapter that wraps the manager
- `cleanup.py` is a 24-line maintenance task tied to the manager lifecycle

### Directory layout after refactor
```
sandbox/
  __init__.py
  manager.py
  provider.py
  cleanup.py
  models/
    __init__.py
    models.py
    errors.py
    config.py
  containers/
    __init__.py
    compose.py
    podman.py
  filesystem/
    __init__.py
    snapshots.py
```

### Not recommended
- Grouping `manager.py` and `provider.py` into a `core/` sub-package — "core" is vague and hiding the main orchestrator one level deep makes imports harder
- Moving `cleanup.py` into a `maintenance/` directory for a single 24-line file — over-engineering
