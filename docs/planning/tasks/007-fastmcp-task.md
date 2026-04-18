# FastMCP 3.0 Completion Plan

This document outlines the remaining tasks to fully complete the FastMCP 3.0 upgrade for the `syntx-memory` MCP server, building on the partially implemented features from docs/005-fastmcp-upgrade-plan.md. It factors in the upcoming agents refactor (docs/006-agents-refactor.md), which will reorganize agents into subfolders and require import updates.

## Overview

Current status: Phases 1 and 2 are complete, Phase 3 is ~70% done. Remaining work focuses on interactivity enhancements, polish, and advanced features.

## Updated Migration Steps (Accounting for Agents Refactor)

### 1. Complete Agents Refactor (Prerequisite)
- Execute the agents folder refactor as described in docs/006-agents-refactor.md
- Move agents to subfolders: `audit/`, `map/`, `fix/`, `validate/`, `document/`
- Update all imports in FastMCP tools and dependent files (e.g., `from ...agents.audit.audit_agent` and `from ...agents.document.task_agent`)

### 2. Phase 3 Completion: Full Interactivity
- **User Elicitation**: Add `ctx.request_input()` for destructive operations
  - Implement in `memory_manage` tool for deletion confirmations
  - Add to `audit_package` for critical decisions
  - Update triage tool for escalation confirmations

### 3. Phase 4: Polish (Icons, Rich Content & Tasks)
- **Icons**: Add `Icon` objects to all tools and server
  - Use FastMCP's `Image` utility for local assets
  - Assign appropriate icons (e.g., audit tools get magnifying glass, memory tools get brain)
- **Rich Content**: Enable multi-part responses
  - Return text + images/diagrams in `diagram_agent` calls
  - Add progress bars and tables for long-running operations
- **Background Tasks**: Convert heavy tools to `task=True`
  - Add to `audit_package`, `map_codebase`, `triage_violations`
  - Ensure proper task lifecycle management

### 4. Phase 5: Knowledge Graph Dashboard (Advanced UI)
- **Interactive ForceGraph**: Build zoomable graph visualization
  - Memory nodes: Facts and patterns
  - Code nodes: Functions/classes from `map_codebase`
  - Jina nodes: Tickets via new `Jina Embedder` service
  - Relationships: `AFFECTS`, `IMPLEMENTS`, `MENTIONS`, `RESOLVES`
- **Jina Code Embedder**: Implement semantic ticket linking
  - Use `hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M` model
  - Lazy-load with VRAM management (TTL 5min, manual unload)
- **File Explorer Tab**: TreeView with violation markers
- **Integration**: Launch via `fastmcp dev apps`, update graph during CLI operations

### 5. Additional Enhancements
- **Versioning**: Add version ranges to components
- **Website URL**: Add `website_url` to server config
- **OpenTelemetry Integration**: Ensure spans wrap all FastMCP components
- **Testing**: Validate all new features with MCP inspector

## Implementation Order

1. **Post-Refactor Updates**: Update imports immediately after agents refactor
2. **Interactivity**: Complete user elicitation (Phase 3)
3. **Polish**: Icons, rich content, background tasks (Phase 4)
4. **Dashboard**: Full UI implementation (Phase 5)
5. **Testing & Documentation**: End-to-end validation and docs updates

## Dependencies

- Agents refactor must complete first
- Jina Embedder requires Ollama setup
- Dashboard may need additional frontend dependencies

## Success Criteria

- All FastMCP 3.0 features from docs/005-fastmcp-upgrade-plan.md implemented
- Agents refactor integrated without breaking changes
- Server passes all tests with new features
- Dashboard provides visual graph exploration
- Icons and rich content enhance client experience

## Timeline

- Phase 3: 1-2 days
- Phase 4: 2-3 days  
- Phase 5: 1-2 weeks (complex UI integration)

This plan ensures the server fully leverages FastMCP 3.0 while maintaining compatibility with the refactored agent architecture.</content>
<parameter name="filePath">docs/007-fastmcp-task.md