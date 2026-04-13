# Changelog

All notable changes to this project will be documented in this file.

The repository had multiple planned phases in flight before changelog tracking was introduced. The entries below only describe capabilities that are present in the codebase at the time of writing.

## [0.2.0] - 2026-04-14

### Added
- Centralized server version metadata sourced from the package version instead of a hard-coded runtime string.
- Stable server metadata surfaces through FastMCP metadata, the `get_server_info` tool, and `GET /info`.
- Configurable website URL support via `MEM_GRAPH_WEBSITE`.
- Formal changelog tracking for released and in-progress work.

### Documented
- Version and website metadata flow for operators and clients.

## [0.1.0] - Initial baseline

### Added
- Core memory, work, notes, filesystem, audit, graph, background-task, and integration tool surfaces.
- Knowledge-graph dashboard and file-explorer HTTP surfaces.
- Jira issue embedding and code-linking support.

### Notes
- This baseline entry summarizes features that already existed before changelog tracking started, rather than reconstructing a detailed release-by-release history.