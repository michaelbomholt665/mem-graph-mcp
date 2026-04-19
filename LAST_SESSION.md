# Last Session Summary

**Date:** 2026-04-18
**Task:** 024 — Thread-Safe Universal Tree-sitter Parser, Extractor, Resolver, and Ladybug Persistence

## What was implemented

### New files created

**Parser package** (`src/mem_graph/app/parsers/`):

- `types.py` — All pipeline DTOs: `ParseLimits`, `DEFAULT_LIMITS`, `NodeKind`, `EdgeKind`, `ParseRequest`, `ParseResult`, `ParsedFile`, `ExtractedNode`, `ExtractedEdge`, `SymbolRef`, `AnonymousSymbol`, `ImportRef`, `CallRef`, `ResolutionResult`, `PersistenceResult`
- `assets.py` — Grammar asset discovery and validation; `GrammarManifest`, `_AssetRegistry` (process-wide singleton with bounded lock-protected cache); `language_for_path()`; `get_manifest()`; extension → language key mapping for all 16 supported grammars
- `safety.py` — `SafetyContext` per-call counter with deadline checks for nodes, captures, symbols, edges, resolver passes, parse duration; `check_file_size()`; `LeakSnapshot` for safety tests
- `loader.py` — ctypes-based `.so` loading via `tree_sitter_{lang}` C symbol; bounded `Language` cache (32 entries) and `Query` cache (64 entries) both lock-protected; `parse_bytes()` returns `(ParseResult, ParsedFile | None)`; `cache_sizes()`; `clear_caches()`
- `pipeline.py` — Orchestrator: `parse_file()`, `extract_file()`, `index_file()`, `index_tree()`; extractor + resolver registries; never executes DB queries directly
- `persist.py` — Pure DTO → Cypher batch builder; `CypherBatch`, `NodeBatch`, `EdgeBatch`, `FileBatch` DTOs; deterministic `symbol_id()` and `file_id()` via SHA-256[:32]; Cypher upsert templates for `CodeFile`, `CodeSymbol`, and 9 relationship types using `OPTIONAL MATCH` + conditional `CREATE` (no `MERGE`); `build_batch()`
- `ingest.py` — Single Ladybug execution boundary; `ingest_batch(db, batch)` creates a fresh `lb.Connection` per call; retry logic with `max_retries`; structured `PersistenceResult`; never raises raw Ladybug exceptions

**Extractor sub-package** (`src/mem_graph/app/parsers/extractors/`):

- `base.py` — `BaseExtractor` ABC; `make_symbol_id()`, `make_file_id()`, `make_file_symbol()`, `make_file_edge()`, `make_contains_edge()`, `node_text()`, `node_line_start()`, `node_line_end()`
- `scm.py` — `ScmExtractor`: runs canonical `{language}.scm` query via `language.query().captures()`; maps capture names to `NodeKind` via prefix table
- `universal.py` — `UniversalExtractor`: tries SCM first, falls back to bounded depth-3 AST walk; covers css, go.mod, go.sum, html, java, javascript, json, proto, toml, yaml
- `python.py` — `PythonExtractor`: full AST traversal for class, function/method (sync+async), import, import_from, constants, lambda assignments, call sites
- `go.py` — `GoExtractor`: package, function_declaration, method_declaration (with receiver), struct/interface type_spec, import_declaration, var_declaration (exported), goroutine (go statement), call_expression
- `typescript.py` — `TypeScriptExtractor`: function, class + class members, interface, type_alias, enum, import, export unwrapping, lexical_declaration → arrow_function / variable, call_expression; is_async detection
- `tsx.py` — `TsxExtractor`: inherits TypeScriptExtractor + JSX walk for custom components (capitalized tag names emit `CALL` symbols with `capture_reason="jsx_component"`)
- `cypher.py` — `CypherExtractor`: clause-level symbols (MATCH, CREATE, MERGE, etc.); gracefully skips if wrong grammar binary detected (Haskell binary known issue from Task 023)
- `sql.py` — `SqlExtractor`: statement nodes, CTEs, table references, function invocations; uses grammar's actual short node names (select, cte, relation, invocation)

**Resolver sub-package** (`src/mem_graph/app/parsers/resolvers/`):

- `base.py` — `BaseResolver` ABC; `build_index()` name→[node] lookup
- `imports.py` — `ImportResolver`: resolves import symbols by name index; filesystem relative import resolution for Python and TypeScript/TSX
- `symbols.py` — `SymbolResolver`: emits `EXTENDS` and `IMPLEMENTS_SYMBOL` edges from `node.extra["extends"]` / `["implements"]`
- `calls.py` — `CallResolver`: resolves CALL nodes to FUNCTION/METHOD/ARROW_FUNCTION symbols by name (exact then short name); emits `RESOLVES_TO` with confidence
- `anonymous.py` — `AnonymousSymbolResolver`: connects anonymous/closure/goroutine symbols to parent scope via `CONTAINS`
- `python.py` — `PythonResolver`: method → class containment via qualified name prefix
- `go.py` — `GoResolver`: method receiver → struct/interface containment
- `typescript.py` — `TypeScriptResolver`: class/interface `EXTENDS` and `IMPLEMENTS_SYMBOL` via `extra` dict
- `query_lineage.py` — `QueryLineageResolver`: CTE → query `CONTAINS`; table → query `READS_FROM`; table → CTE `ALIASES` when names match

**MCP tools** (`src/mem_graph/tools/code/`):

- `__init__.py`
- `parser.py` — `FastMCP("code")` with `namespace:code` tag (lazy-loaded); 5 tools:
  - `parser_health` — grammar assets, binary checksums, cache sizes, default limits
  - `parser_parse_file` — parse-only, no persist
  - `extract_code_symbols` — parse + extract, symbol summary, no persist
  - `index_code_symbols` — full pipeline for one file including Ladybug ingest
  - `index_code_tree` — bounded recursive tree indexing with include/exclude globs

### Schema changes (`schema/agent_memory_schema.cypher`)

- Added `INSTALL llm; LOAD llm;` and `INSTALL algo; LOAD algo;` to extensions block
- Updated `CodeSymbol` node table to add: `qualified_name STRING`, `parent_id STRING`, `line_start INT64`, `line_end INT64`, `is_exported BOOLEAN DEFAULT false`, `is_async BOOLEAN DEFAULT false`
- Added 14 new code graph relationship tables: `FILE_SYMBOL`, `CONTAINS`, `IMPORTS`, `CALLS`, `RESOLVES_TO`, `EXTENDS`, `IMPLEMENTS_SYMBOL`, `HAS_TYPE`, `RETURNS_TYPE`, `READS_FROM`, `PROJECTS`, `FILTERS_ON`, `JOINS_ON`, `ALIASES`

### Migration (`src/mem_graph/db.py`)

- Added `_migrate_schema` entries for 6 new CodeSymbol columns: `qualified_name`, `parent_id`, `line_start`, `line_end`, `is_exported`, `is_async`
- Updated `_bootstrap` to attempt `llm` and `algo` extension install/load (graceful failure — ignored if unavailable in current Ladybug build)

### Server wiring

- `src/mem_graph/server.py` — imported `code_parser` from `tools/code/parser.py`; added `code_parser.mcp` to the sub-mcp mount list
- `src/mem_graph/app/constants.py` — added `"code"` to `LAZY_NAMESPACES`
- `src/mem_graph/app/parsers/__init__.py` — exposes `parse_file`, `extract_file`, `index_file`, `index_tree` as public API

## Architecture compliance

- Thread-safety: all grammar caches are lock-protected; no shared mutable parser state
- No subprocesses or shell-outs at runtime
- No unbounded loops; all walks are depth- or count-bounded via `SafetyContext`
- Single DB execution boundary: only `ingest.py` talks to Ladybug
- MCP tools call only `pipeline.py`; no direct imports of `persist.py` or `ingest.py` from tools
- `persist.py` is pure (no connections, no execution); testable without live DB
- `ingest.py` accepts `lb.Database` as a dependency; creates its own `lb.Connection` per call

## Open items carried forward

- Cypher grammar binary is still a mis-packaged Haskell parser; `CypherExtractor` gracefully skips but real Cypher extraction requires sourcing a correct binary
- Embedding dimension reconciliation (OLLAMA_CODE_EMBED_DIM vs schema FLOAT[dim]) is not yet done; `ingest.py` does not yet write embeddings — that requires Phase 5 wiring with `CodeEmbedService`
- `CodeEmbedService.upsert_code_file` still has a separate DB write path (BLOCKER from plan 024); not resolved in this session
- `HAS_TYPE`, `RETURNS_TYPE`, `PROJECTS`, `FILTERS_ON`, `JOINS_ON` relationship templates are defined in schema but not yet emitted by extractors (reserved for future resolver passes)
- SCC / cycle detection workflow not yet wired (schema supports `algo` extension)

## ruff / mypy

Both `ruff check .` and `mypy .` exit 0 with no issues.
