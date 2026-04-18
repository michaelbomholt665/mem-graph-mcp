# Design: Versioning & Website URL

**Status:** Design Phase  
**Priority:** Low (Polish)  
**Date:** 2026-04-13

---

## Overview

This design adds version management and official website URL to the server configuration. This enables:

1. **Version Tracking:** Know which version is deployed
2. **API Versioning:** Support multiple API versions as the system evolves
3. **Website Link:** Point users to documentation/support

---

## Goals

1. **Clear Versioning:** Semantic versioning for releases
2. **Backward Compatibility:** Support old API versions (gracefully)
3. **User Documentation:** Link to official resources

---

## Scope

### In Scope
- Add version to `pyproject.toml`
- Expose version in FastMCP server info
- Add website URL to server config
- Add API version header to responses
- Support version negotiation in client requests

### Out of Scope
- Multiple simultaneous API versions (future)
- Version-specific tool selection (not needed yet)
- Deprecation warnings (not yet)

---

## Architecture

### 1. Version Configuration

```python
# pyproject.toml

[project]
name = "memory"
version = "0.2.0"  # Semantic versioning: MAJOR.MINOR.PATCH
description = "Memory-augmented code analysis and refactoring"
```

### 2. Version Exposure in Server

```python
# src/mem_graph/__init__.py

__version__ = "0.2.0"

# src/mem_graph/server.py

from . import __version__

# Read version
SERVER_VERSION = __version__
SERVER_WEBSITE = os.getenv(
    "MEM_GRAPH_WEBSITE",
    "https://github.com/your-org/mem-graph"
)

# Expose in server info
mcp = FastMCP(
    name="mem-graph",
    description="Memory-augmented code analysis and refactoring",
    version=SERVER_VERSION,
    website_url=SERVER_WEBSITE,
    icon=SERVER_ICON,
)

# Expose via API
@mcp.tool()
async def get_server_info() -> dict:
    """Get server information."""
    
    return {
        "name": "mem-graph",
        "version": SERVER_VERSION,
        "website": SERVER_WEBSITE,
        "api_version": "1.0",
        "features": [
            "Fast MCP 3.0",
            "Pydantic-Graph",
            "Hindsight Memory",
            "OpenTelemetry",
        ],
    }
```

### 3. API Version Header

Add version info to all tool responses:

```python
# src/mem_graph/tools/decorators.py

def versioned_tool(tool_name: str, api_version: str = "1.0"):
    """Decorator to add version info to tool responses."""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Wrap result with version info
            if isinstance(result, dict):
                result["_metadata"] = {
                    "api_version": api_version,
                    "timestamp": datetime.now().isoformat(),
                }
            
            return result
        
        return wrapper
    
    return decorator

# Use on tools
@mcp.tool()
@versioned_tool("memory_store", api_version="1.0")
async def memory_store(content: str, tags: list[str] | None = None) -> dict:
    """Store a fact."""
    ...
```

### 4. Version Negotiation

Allow clients to request specific API versions:

```python
# Client code (example)
# Request: Accept-Version: 1.0

# Server response includes version in response metadata
{
    "data": {...},
    "_metadata": {
        "api_version": "1.0",
        "timestamp": "2026-04-13T10:30:00Z",
        "server_version": "0.2.0",
    }
}
```

### 5. CHANGELOG

Maintain version history:

```markdown
# CHANGELOG

## [0.2.0] - 2026-04-13

### Added
- Pydantic-AI-Slim integration for lightweight agents
- Pydantic-Graph for type-safe ReAct workflows
- Pydantic-Deep for planning and self-correction
- Pydantic-AI-Skills for Python-native programmatic skills
- Hindsight integration for long-term memory
- Phase 3: User elicitation with ctx.request_input()
- Phase 4a: Icons and rich content visualization
- Phase 4b: Background tasks with task=True
- Phase 5a: Knowledge graph dashboard with ForceGraph
- Phase 5b: Jina code embedder for semantic ticket linking
- Phase 5c: File explorer tab with violation markers
- OpenTelemetry integration for full observability
- Versioning and website URL support

### Fixed
- Orchestra graph now uses Pydantic-Graph for resumability
- Improved memory recall accuracy with new embedding model

### Changed
- Agent factory now uses tier-based model selection
- Tools reorganized as Python-native skills

## [0.1.0] - 2026-03-01

### Added
- Initial FastMCP 3.0 implementation
- Core Five agents (Audit, Map, Fix, Validate, Document)
- Knowledge graph integration with Kuzu/Ladybug
- CodeMode transformation for AI accessibility
- Lazy namespaces for tool discovery
```

---

## Configuration

```bash
# .env

# Server version and metadata
MEM_GRAPH_VERSION=0.2.0
MEM_GRAPH_WEBSITE=https://github.com/your-org/mem-graph
MEM_GRAPH_API_VERSION=1.0
```

---

## Implementation Checklist

- [ ] Define `__version__` in `src/mem_graph/__init__.py`
- [ ] Update `pyproject.toml` with version
- [ ] Add version to FastMCP server info
- [ ] Create `get_server_info` tool
- [ ] Add `_metadata` to tool responses via decorator
- [ ] Add website URL to config
- [ ] Create CHANGELOG.md
- [ ] Test version info is exposed correctly

---

## Success Criteria

1. Version is defined in one place (no duplication)
2. Server info includes version and website URL
3. Tool responses include API version metadata
4. CHANGELOG is up-to-date

---

## Semantic Versioning

Follow [SemVer 2.0.0](https://semver.org/):

- **MAJOR:** Breaking changes (e.g., tool schema changes)
- **MINOR:** New features, agent behavior improvements
- **PATCH:** Bug fixes, minor improvements

Examples:
- `0.1.0` → `0.2.0`: New Phase 3-5 features (MINOR bump)
- `0.2.0` → `1.0.0`: When API is stable (MAJOR bump)
- `0.2.0` → `0.2.1`: Bug fix in Hindsight (PATCH bump)

---

## Notes

- Version is mainly for user information (not enforced programmatically)
- Website URL should point to README, docs, or support page
- CHANGELOG helps users understand what changed between versions
