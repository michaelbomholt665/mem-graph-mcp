# Task 024: Thread-Safe Universal Tree-sitter Parser, Extractor, Resolver, and Ladybug Persistence

**Status:** Planning  
**Priority:** High  
**Blocked by:** Tree-sitter Python runtime dependency, Ladybug schema migration, and DB ingest boundary decision  
**Blocks:** Code symbol graph indexing, code impact analysis, query lineage indexing, MCP parser tooling

## Problem Statement

Build a universal Tree-sitter parser pipeline that turns supported source files into a compact semantic graph and persists that graph into Ladybug using `schema/agent_memory_schema.cypher` as the storage contract.

Database writes must be consolidated behind one file:

```text
src/mem_graph/app/parsers/ingest.py
```

Rule: if code sends a query to Ladybug, it lives in `ingest.py`. `persist.py` only builds statements and batch DTOs. `pipeline.py` calls `ingest.py` at the end of the chain. MCP tools call `pipeline.py` only.

The parser must be safe to run inside the MCP server process:

- Thread-safe under concurrent tool calls.
- Leak-free for parser, query, tree, cursor, and source-buffer lifetimes.
- No subprocesses, worker processes, shell-outs, or background daemons.
- No "ghost" processes or unjoined threads.
- No unbounded parse, extraction, resolver, or persistence loops.
- No unbounded memory growth from AST retention, query capture retention, source text retention, or global caches.
- No process-wide mutation after initialization except bounded, lock-protected caches.

The implementation location is:

```text
src/mem_graph/app/parsers/
```

Do not implement in this task update. This document is the implementation plan.

## Authoritative Asset Layout

Grammar assets are already present under:

```text
data/tree-sitter/grammar/{language}/
```

Each supported language directory contains:

```text
data/tree-sitter/grammar/{language}/*.so
data/tree-sitter/grammar/{language}/manifest.json
data/tree-sitter/grammar/{language}/node-types.json
data/tree-sitter/grammar/{language}/queries/{language}.scm
```

Supported language directory names and query file names:

| Language key | Binary location | Query location |
| --- | --- | --- |
| `css` | `data/tree-sitter/grammar/css/*.so` | `data/tree-sitter/grammar/css/queries/css.scm` |
| `cypher` | `data/tree-sitter/grammar/cypher/*.so` | `data/tree-sitter/grammar/cypher/queries/cypher.scm` |
| `go` | `data/tree-sitter/grammar/go/*.so` | `data/tree-sitter/grammar/go/queries/go.scm` |
| `go.mod` | `data/tree-sitter/grammar/go.mod/*.so` | `data/tree-sitter/grammar/go.mod/queries/go.mod.scm` |
| `go.sum` | `data/tree-sitter/grammar/go.sum/*.so` | `data/tree-sitter/grammar/go.sum/queries/go.sum.scm` |
| `html` | `data/tree-sitter/grammar/html/*.so` | `data/tree-sitter/grammar/html/queries/html.scm` |
| `java` | `data/tree-sitter/grammar/java/*.so` | `data/tree-sitter/grammar/java/queries/java.scm` |
| `javascript` | `data/tree-sitter/grammar/javascript/*.so` | `data/tree-sitter/grammar/javascript/queries/javascript.scm` |
| `json` | `data/tree-sitter/grammar/json/*.so` | `data/tree-sitter/grammar/json/queries/json.scm` |
| `proto` | `data/tree-sitter/grammar/proto/*.so` | `data/tree-sitter/grammar/proto/queries/proto.scm` |
| `python` | `data/tree-sitter/grammar/python/*.so` | `data/tree-sitter/grammar/python/queries/python.scm` |
| `sql` | `data/tree-sitter/grammar/sql/*.so` | `data/tree-sitter/grammar/sql/queries/sql.scm` |
| `toml` | `data/tree-sitter/grammar/toml/*.so` | `data/tree-sitter/grammar/toml/queries/toml.scm` |
| `tsx` | `data/tree-sitter/grammar/tsx/*.so` | `data/tree-sitter/grammar/tsx/queries/tsx.scm` |
| `typescript` | `data/tree-sitter/grammar/typescript/*.so` | `data/tree-sitter/grammar/typescript/queries/typescript.scm` |
| `yaml` | `data/tree-sitter/grammar/yaml/*.so` | `data/tree-sitter/grammar/yaml/queries/yaml.scm` |

Important naming constraint: `go.mod` and `go.sum` are literal language keys, directory names, and `.scm` basenames. Do not normalize them to `gomod`, `gosum`, or `go`.

## Current Repository State

- `src/mem_graph/app/parsers/` exists and currently contains `query_codegen.py` and `query_validate.py`.
- The parser runtime dependency still needs to be added to `pyproject.toml`.
- `CodeFile` and `CodeSymbol` already exist in `schema/agent_memory_schema.cypher`.
- `CodeSymbol` currently lacks source-span fields needed by parser output.
- Existing graph/dashboard code already knows about `CodeFile`, `CodeSymbol`, `HAS_FILE`, `BACKEND_SYMBOL`, `SYMBOL_TASK`, `SYMBOL_VIOLATION`, and `SYMBOL_DECISION`.
- New code graph relationships must be added deliberately and then surfaced where graph snapshots enumerate relationship types.

## Target Architecture

Build out the parser package as a pure in-process library plus a thin MCP tool layer:

```text
src/mem_graph/app/parsers/
  __init__.py
  assets.py
  loader.py
  safety.py
  types.py
  pipeline.py
  persist.py
  ingest.py
  extractors/
    __init__.py
    base.py
    universal.py
    scm.py
    python.py
    go.py
    typescript.py
    tsx.py
    cypher.py
    sql.py
  resolvers/
    __init__.py
    base.py
    anonymous.py
    imports.py
    symbols.py
    calls.py
    typescript.py
    python.py
    go.py
    query_lineage.py
```

Expose MCP tools from the existing tool registration pattern, preferably under a parser/code namespace:

```text
src/mem_graph/tools/code/
  __init__.py
  parser.py
```

Candidate MCP tools:

- `parser_health`
- `parse_file`
- `extract_code_symbols`
- `index_code_symbols`
- `index_code_tree`

The MCP surface should call the parser pipeline only through stable DTOs. It should not expose raw Tree-sitter objects.

## Module Responsibility Table

| Module | Owns | Must not own |
| --- | --- | --- |
| `assets.py` | Grammar/query asset discovery and validation | Parser execution, DB access |
| `loader.py` | Tree-sitter language/query loading and parse calls | Semantic extraction, DB access |
| `safety.py` | Limits, counters, deadlines, safety diagnostics | Business logic or DB access |
| `types.py` | DTO definitions shared by parser pipeline | Ladybug connection objects |
| `extractors/*` | AST/query capture to semantic DTOs | Persistence or DB execution |
| `resolvers/*` | Import, call, anonymous-symbol, type, and lineage resolution | Persistence or DB execution |
| `persist.py` | Pure DTO -> Cypher statement/batch construction | Opening connections, transactions, retries, executing queries |
| `ingest.py` | The only Ladybug execution boundary | Parsing, extraction, raw AST traversal |
| `pipeline.py` | Orchestration of parse -> extract -> resolve -> ingest | Direct DB queries or direct imports from MCP tools |
| MCP tools | User-facing tool DTOs and calls into `pipeline.py` | Direct imports from `persist.py` or `ingest.py` |

This split gives two clean test seams:

- `persist.py` can be tested without a live database.
- `ingest.py` can be tested against a real or mock Ladybug connection without running Tree-sitter.

## Runtime Safety Requirements

### Parser Object Ownership

- Treat `Language`, compiled `Query`, and immutable asset metadata as process-wide, read-only, bounded cache entries.
- Do not share mutable `Parser`, `TreeCursor`, or capture iteration state across threads.
- Prefer one parser instance per parse call, or a small lock-protected/thread-local parser pool if parser construction is too expensive.
- Do not store `Tree` objects beyond the extraction call.
- Do not store source bytes beyond the parse/extract call unless the existing `CodeFile` content pipeline explicitly owns that retention.

### Bounded Execution

Every public parse/index path must enforce:

- Maximum file size.
- Maximum parse duration.
- Maximum AST node count visited.
- Maximum query captures processed.
- Maximum extracted symbols per file.
- Maximum extracted edges per file.
- Maximum resolver passes.
- Maximum persistence batch size.

Timeout behavior should return a structured partial/failure result and must not leave retained ASTs, cursors, or queued work behind.

### No Process Leakage

The implementation must not:

- Spawn child processes.
- Start unmanaged threads.
- Depend on shell commands at runtime.
- Open file descriptors without deterministic close.
- Keep references to trees, cursors, large source buffers, or capture lists in module globals.
- Use `atexit`, daemon threads, multiprocessing pools, or background queues for parser work.

### Cache Policy

Allowed caches:

- Grammar manifest metadata by language key.
- Loaded `Language` objects by `(language_key, binary_path, checksum)`.
- Compiled query objects by `(language_key, query_path, checksum)`.
- Extension-to-language mapping.

Required cache constraints:

- Bounded size.
- Lock-protected or initialized once before concurrent use.
- Explicit `parser_health` visibility into loaded languages, query availability, and cache sizes.
- Test coverage for repeated parse/index calls to catch growth.

## Core Modules

1. `assets.py`
   - Own grammar root discovery: `data/tree-sitter/grammar`.
   - Enumerate only the supported language keys listed above.
   - Locate exactly one intended `.so` per language, `manifest.json`, `node-types.json`, and `queries/{language}.scm`.
   - Validate binary checksums from `manifest.json` before loading.
   - Normalize file extensions to language keys without changing literal `go.mod` and `go.sum` keys.

2. `loader.py`
   - Load shared grammar binaries from the asset directory.
   - Compile and cache query files.
   - Provide `parse_bytes(language_key, content, *, limits) -> ParsedTree`.
   - Keep Tree-sitter runtime objects behind a small API so the rest of the package uses DTOs.

3. `safety.py`
   - Define parse/index limits.
   - Implement deadline checks and counters.
   - Provide helpers to stop extraction/resolution cleanly when limits are exceeded.
   - Provide leak/regression diagnostics for tests, such as repeated-run memory deltas.

4. `types.py`
   - Define stable internal DTOs:
     - `ParseRequest`
     - `ParseResult`
     - `ParsedFile`
     - `ExtractedNode`
     - `ExtractedEdge`
     - `SymbolRef`
     - `AnonymousSymbol`
     - `ImportRef`
     - `CallRef`
     - `ResolutionResult`
     - `PersistenceResult`
   - Keep DTOs independent from Ladybug and FastMCP.

5. `extractors/`
   - Implement a universal query-backed extractor for simple grammars.
   - Implement custom extractors for Python, Go, TypeScript, TSX, Cypher, and SQL.
   - Avoid emitting punctuation, comments, literals, expression internals, and unresolved identifier spam.

6. `resolvers/`
   - Resolve imports, symbols, calls, inheritance, and query lineage.
   - Include an anonymous-symbol resolver for Go, Python, and TypeScript.
   - Emit confidence-scored resolution edges.

7. `pipeline.py`
   - Orchestrate parse -> extract -> resolve -> ingest.
   - Provide public APIs:
     - `parse_file(path, language=None, limits=None)`
     - `extract_file(path, language=None, limits=None)`
     - `index_file(root, path, project_id=None, backend_id=None, limits=None)`
     - `index_tree(root, include=None, exclude=None, project_id=None, backend_id=None, limits=None)`
   - Call `ingest.py` for persistence at the end of indexing APIs.
   - Never execute DB queries directly.
   - Never import or use `persist.py` directly from MCP tools.
   - Return structured results with counts, warnings, limit hits, and persistence status.

8. `persist.py`
   - Convert DTOs to idempotent Cypher statement/batch DTOs.
   - Use deterministic IDs from file path, language, node kind, qualified name, anonymous key, and source span.
   - Build batches in required order: `CodeFile`, then `CodeSymbol`, then relationships.
   - Generate explicit `MATCH` then `CREATE`/`SET` statement plans because Ladybug does not support `MERGE`.
   - Generate `UNWIND` batch plans where supported.
   - Never open a DB connection.
   - Never execute a query.
   - Never import Ladybug connection classes.

9. `ingest.py`
   - Own all Ladybug DB interactions for parser ingest.
   - Accept the shared process-wide `lb.Database` as a dependency; never create its own `Database` internally.
   - Receive `project_id` or resolved project root at initialization, locate the active `.lbug` file under `{project_root}/data/*.lbug`, and validate it matches the server's active database.
   - Create a fresh synchronous `lb.Connection(db)` per ingest call.
   - Do not use `AsyncConnection`; this is local embedded storage and write serialization matters more than async network latency.
   - Execute statement/batch DTOs produced by `persist.py`.
   - Own explicit `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK`.
   - Own bounded batch sizing, retries, partial failure reporting, stale cleanup, and structured `PersistenceResult`.
   - Return structured errors; never raise raw Ladybug exceptions across the parser pipeline boundary.

## Universal Extraction Strategy

Use `queries/{language}.scm` as the first extraction mechanism for all supported grammars. The query files are now treated as present assets, not optional future artifacts.

For simple/config grammars, the universal extractor should produce shallow graph nodes:

- `css`
- `go.mod`
- `go.sum`
- `html`
- `java`
- `javascript`
- `json`
- `proto`
- `toml`
- `yaml`

For semantic-heavy grammars, use the query captures plus AST context and custom resolver logic:

- `python`
- `go`
- `typescript`
- `tsx`
- `cypher`
- `sql`

The target average for normal source files remains compact: roughly 6 semantic nodes and 12 semantic edges per typical file, with deliberate exceptions for dense modules, schema files, and query files.

## Anonymous Symbol Extraction and Resolution

Anonymous symbols are source constructs that do not have a stable declared name but still matter for code navigation, dependency analysis, or call resolution. Go, Python, and TypeScript must have explicit anonymous-symbol support.

### Shared Anonymous-Symbol Contract

Each anonymous symbol should include:

- `kind`: anonymous function, lambda, closure, callback, inline type, object literal, interface literal, goroutine closure, decorator wrapper, or language-specific equivalent.
- `display_name`: deterministic readable name, such as `<lambda>@module:12`, `<closure>@pkg.Func:44`, or `<callback>@Component.props.onClick:31`.
- `qualified_name`: deterministic path including parent scope and source span.
- `parent_symbol_id`: containing function, method, class, module, or file.
- `line_start` and `line_end`.
- `capture_reason`: why it is semantically useful.
- `stable_id_key`: file path, language, parent qualified name, node kind, and source span.

Anonymous symbols should be emitted only when they affect semantics:

- Passed as a callback.
- Returned from a function.
- Assigned to a module/class/package-level binding.
- Launched as a goroutine.
- Used as a decorator/wrapper.
- Used as a React handler/component callback.
- Required to resolve a call edge.

Do not emit every local lambda, object literal, or closure by default.

### Python Anonymous Symbols

Extractor responsibilities:

- Capture `lambda` nodes when assigned, returned, passed as callback, or nested inside exported/public functions.
- Capture nested functions when returned, passed, decorated, or used as closures.
- Capture decorator wrappers when wrapper functions are nested and returned.
- Attach anonymous/nested symbols to the nearest module, class, function, or method scope.

Resolver responsibilities:

- Resolve calls through local assignments to lambdas/nested functions.
- Resolve decorators to wrapper symbols where obvious.
- Connect callbacks to call sites using `CALLS` and `RESOLVES_TO` when confidence is sufficient.

### Go Anonymous Symbols

Extractor responsibilities:

- Capture function literals.
- Distinguish goroutine closures launched by `go func(...) { ... }`.
- Distinguish deferred closures launched by `defer func(...) { ... }`.
- Capture function literals assigned to package variables or struct fields.
- Capture function literals passed as callbacks.

Resolver responsibilities:

- Connect goroutine/defer anonymous symbols to their containing function.
- Resolve calls inside closures against lexical scope, receiver scope, package scope, and imports.
- Connect function literals assigned to names so later calls can resolve to the anonymous symbol.

### TypeScript Anonymous Symbols

Extractor responsibilities:

- Capture arrow functions and function expressions when assigned, exported, returned, passed as callbacks, or used as React handlers.
- Capture inline object/class/type/interface literals only when exported, assigned to top-level bindings, or used as meaningful structural contracts.
- Capture JSX callback props such as event handlers when they are local anonymous functions with semantic call edges.

Resolver responsibilities:

- Resolve anonymous callbacks through variable bindings, props, imports, and lexical scope.
- Resolve member-expression calls inside anonymous functions.
- Connect React/TSX component usage to local/imported components and callback props where confidence is sufficient.

## Language Plans

### Python

Extractor responsibilities:

- Create symbols for module/file, class, function, method, import, call, type alias, selected module constants, and qualifying anonymous symbols.
- Detect async functions and awaited calls.
- Associate decorators with the function/class they decorate.
- Exclude ordinary local variables unless they are exported constants, dependency injection boundaries, or anonymous-symbol bindings.

Resolver responsibilities:

- Resolve relative and absolute imports to `CodeFile` and module symbols inside the indexed root.
- Build qualified names: `module.Class.method`, `module.function`, and deterministic anonymous names.
- Resolve calls by lexical scope, containing class/module, imported aliases, anonymous bindings, then unresolved external.
- Mark awaited calls.

### Go

Extractor responsibilities:

- Create symbols for package, function, method, struct, interface, import, call, goroutine, defer, channel, and qualifying anonymous function literals.
- Attach method receiver type to method symbols.
- Store exported status from identifier capitalization.
- Capture interface method declarations when they form public contracts.
- Exclude local variables except short declarations that bind functions, channels, errors crossing boundaries, or anonymous function literals.

Resolver responsibilities:

- Resolve imports using package path and module root when `go.mod` is available.
- Resolve selector calls such as `pkg.Func`, `receiver.Method`, and chained calls as best-effort.
- Connect methods to receiver structs/interfaces.
- Connect goroutine/defer closure symbols to call edges.

### TypeScript

Extractor responsibilities:

- Create symbols for module/file, function, method, class, interface, type alias, enum, export, import, variable, arrow function, call, type reference, and qualifying anonymous symbols.
- Store `is_async`, `is_exported`, `visibility`, and `returns_promise` when available.
- Treat React hooks/components as functions unless TSX-specific JSX extraction applies.
- Exclude expression internals, literals, object property noise, and local identifiers without exported, call, or anonymous-symbol relevance.

Resolver responsibilities:

- Resolve import aliases, namespace imports, default imports, and named imports.
- Resolve relative imports to source files using `.ts`, `.tsx`, `.js`, `.jsx`, and `index.*` conventions.
- Resolve class/interface inheritance and implementation edges.
- Resolve calls by lexical scope, imports, class members, member expressions, and anonymous bindings.
- Mark awaited calls and infer unawaited async-call risk after `RESOLVES_TO`.

### TSX

TSX should reuse TypeScript extraction and add JSX-specific behavior:

- Create symbols for components, JSX custom elements, and JSX attributes only when they represent component usage or externally meaningful props.
- Do not store every DOM element by default.
- Store custom components with capitalized names.
- Resolve custom JSX elements to imported or local React components.
- Connect component usage with `CALLS` and attach `call_name` unless a dedicated `RENDERS` relationship is added later.

### Cypher

Extractor responsibilities:

- Create query, clause, node pattern, relationship pattern, label, relationship type, variable, property, parameter, and function-call symbols.
- Classify query type as read, write, or read-write.

Resolver responsibilities:

- Bind aliases to node/relationship patterns within query scope.
- Connect returned/projected variables and properties.
- Connect parameters to query symbols.
- For schema files, optionally resolve labels and relationship types to live schema names.

### SQL

Extractor responsibilities:

- Create statement, CTE, table, column, alias, function-call, subquery, and DML/DDL symbols.
- Store dialect as a property when configured.

Resolver responsibilities:

- Resolve table aliases within statement/CTE scope.
- Connect selected columns to table references where possible.
- Track CTE definitions and references.
- Connect filters, joins, grouping, ordering, and projections.

## Ladybug Schema Plan

Schema updates are a hard prerequisite before parser ingest runs. `ingest.py` must fail closed if the required node tables, relationship tables, vector indexes, or extensions are missing.

### Minimum Required Fix

Update `CodeSymbol` in `schema/agent_memory_schema.cypher` to match parser output and the Pydantic model:

```cypher
line_start INT64,
line_end   INT64,
```

Add a migration in `src/mem_graph/db.py` for existing databases:

```python
("CodeSymbol", "line_start", "INT64"),
("CodeSymbol", "line_end", "INT64"),
```

### Embedding Dimension Fix

The current schema uses fixed-size `FLOAT[1536]` embedding properties for multiple node tables, including `CodeFile` and `CodeSymbol`. The local `.env` currently configures:

```text
OLLAMA_CODE_EMBED_MODEL=hf.co/jinaai/jina-embeddings-v4-text-code-GGUF:Q5_K_M
OLLAMA_TEXT_EMBED_MODEL=hf.co/nomic-ai/nomic-embed-text-v1.5-GGUF:F16
OLLAMA_EMBED_DIM=768
OLLAMA_CODE_KEEP_ALIVE=2m
```

Before parser symbol embeddings are enabled, reconcile the schema with the active embedding dimension. Since Ladybug vector columns are fixed-size arrays, `CodeFile.embedding` and `CodeSymbol.embedding` must use the same dimension as the configured code embedding model output. If the active code embedding model returns 768 dimensions, update these schema columns and vector indexes from `FLOAT[1536]` to `FLOAT[768]`, and add a migration/compatibility plan for existing databases.

Do not let `ingest.py` write embeddings whose length does not match the schema column dimension. Return a structured `PersistenceResult` error instead.

### Required Extensions

Update `schema/agent_memory_schema.cypher` and DB initialization so required extensions are installed/loaded before index creation or algorithm calls:

```cypher
INSTALL vector;
LOAD vector;

INSTALL llm;
LOAD llm;

INSTALL algo;
LOAD algo;
```

Notes:

- The `vector` extension provides `CREATE_VECTOR_INDEX`, `QUERY_VECTOR_INDEX`, and `DROP_VECTOR_INDEX`, and works on vector properties stored on node tables.
- The `llm` extension provides `CREATE_EMBEDDING`, including Ollama provider support. The initial implementation should prefer the existing Python code embedder for parser output, but loading `llm` keeps DB-side embedding available for later migrations or repair jobs.
- The `algo` extension is required for strongly connected components and related projected-graph analysis.
- Some Ladybug versions pre-install/pre-load common extensions such as `algo`, `fts`, `json`, and `vector`; schema/init code should handle already-installed/already-loaded extensions idempotently.

### Recommended Code Graph Extension

Keep `CodeFile` and `CodeSymbol` as the durable storage base for the first implementation. Avoid creating separate node tables for `Function`, `Class`, `Call`, etc.

Store semantic nodes as `CodeSymbol` with `kind` values such as:

- `module`
- `package`
- `function`
- `method`
- `class`
- `interface`
- `struct`
- `type`
- `variable`
- `import`
- `call`
- `anonymous_function`
- `closure`
- `callback`
- `query`
- `table`
- `column`

Proposed relationship tables:

```cypher
CREATE REL TABLE IF NOT EXISTS FILE_SYMBOL   (FROM CodeFile TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS CONTAINS      (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS IMPORTS       (FROM CodeSymbol TO CodeSymbol, module_path STRING, alias STRING, is_relative BOOLEAN);
CREATE REL TABLE IF NOT EXISTS CALLS         (FROM CodeSymbol TO CodeSymbol, call_name STRING, receiver_name STRING, is_awaited BOOLEAN);
CREATE REL TABLE IF NOT EXISTS RESOLVES_TO   (FROM CodeSymbol TO CodeSymbol, confidence DOUBLE, resolver STRING);
CREATE REL TABLE IF NOT EXISTS EXTENDS       (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS IMPLEMENTS_SYMBOL (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS HAS_TYPE      (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS RETURNS_TYPE  (FROM CodeSymbol TO CodeSymbol);
```

For Cypher and SQL lineage:

```cypher
CREATE REL TABLE IF NOT EXISTS READS_FROM    (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS PROJECTS      (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS FILTERS_ON    (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS JOINS_ON      (FROM CodeSymbol TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS ALIASES       (FROM CodeSymbol TO CodeSymbol);
```

After adding schema relationships, update graph snapshot edge definitions so the dashboard can display parser-created edges.

### SCC / Algo Extension Schema Support

Add a planned SCC workflow for code dependency cycles:

```cypher
CALL PROJECT_GRAPH(
    'CodeDependencyGraph',
    ['CodeSymbol'],
    ['CALLS', 'RESOLVES_TO', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS_SYMBOL']
);

CALL strongly_connected_components('CodeDependencyGraph')
RETURN node, group_id;
```

Use the SCC output for cycle detection among symbols/modules after ingest, not during the write transaction. Projected graphs are connection-scoped and should be created/dropped by analysis tools or dashboard queries, not retained as ingest state.

**When SCC runs**: SCC analysis is triggered as a post-ingest callback, after `CodeEmbedService` embedding is complete. It can run on-demand via MCP tool query or automatically after a full indexing session completes. Do not hold the write transaction open for SCC execution.

## Persist and Ingest Plan

### `persist.py`: Pure Statement Builder

`persist.py` stays pure and deterministic:

- Input: parser/resolver DTOs.
- Output: Cypher statement plans and batch DTOs.
- No DB connection.
- No execution.
- No retries.
- No transaction state.
- No Ladybug exception handling.

Responsibilities:

1. Build deterministic IDs:
   - `CodeFile`: reuse existing `code_file_id(relative_path)` behavior where possible.
   - `CodeSymbol`: `sha256(language:path:kind:qualified_name:start:end)[:32]`.
2. Build node batches:
   - `CodeFile` first.
   - `CodeSymbol` second.
3. Build relationship batches only after endpoint IDs are known:
   - `FILE_SYMBOL`
   - `CONTAINS`
   - `IMPORTS`
   - `CALLS`
   - `RESOLVES_TO`
   - Type/inheritance/query-lineage edges.
4. Build stale-symbol cleanup plans:
   - Identify previous symbols for the file.
   - Identify current extraction IDs.
   - Mark safe deletes versus archive/skip candidates.
5. Build embedding update plans:
   - `CodeFile.embedding` and `CodeSymbol.embedding` updates are represented as batch DTOs.
   - Embedding vectors must be length-validated before execution by `ingest.py`.

### `ingest.py`: Single DB Execution Boundary

`ingest.py` is the only parser file that talks to Ladybug.

Database location:

- The database file lives under `{project_id}/data/*.lbug`, where `project_id` is the project root/path known at MCP server startup.
- `project_id` must be passed into `ingest.py` initialization, along with the active shared `lb.Database`.
- `ingest.py` validates the located `.lbug` file against the active database configuration. It must not silently open a second database.

Connection model:

- The process owns one shared `lb.Database`.
- `ingest.py` accepts that shared `Database` dependency.
- Each ingest call creates its own synchronous `lb.Connection(db)`.
- Do not use `AsyncConnection`.
- Do not keep connection-scoped projected graphs or cursors beyond the ingest call.

Write transactions:

- Ladybug allows only one write transaction at a time. Treat parser ingest as a known serialization point.
- Never hold a write transaction open longer than a single bounded batch.
- Use explicit `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` for all multi-statement writes.
- On failure, rollback the current batch, record the error in `PersistenceResult`, and continue or stop according to configured failure policy.

Upsert strategy:

- Do not use `MERGE`; Ladybug does not support it.
- Implement idempotent writes as explicit existence checks: `MATCH` first, then `CREATE` if missing, inside the same transaction.
- Use explicit `SET n.prop = value` per property. Do not use map spread / `+=`.
- Use `UNWIND` for batch node and relationship creation. Do not use `FOREACH`.
- Upsert order is always `CodeFile`, then `CodeSymbol`, then relationships.
- Never create a relationship before both endpoint nodes exist.

Stale symbol cleanup:

- On re-index, delete stale `FILE_SYMBOL` relationship descendants for that file when they no longer appear in the current extraction.
- Do not delete symbols still referenced by `SYMBOL_TASK`, `SYMBOL_DECISION`, or `SYMBOL_VIOLATION`.
- Archive or skip referenced stale symbols until an explicit archival policy exists.

Return value:

- Every ingest call returns `PersistenceResult`.
- Include counts for files written, symbols written, relationships written, embeddings written, stale symbols cleaned, stale symbols archived/skipped, limit hits, retries, batches committed, batches rolled back, and structured errors.
- Never raise raw Ladybug exceptions to `pipeline.py` or MCP tools.

### Code Embedder / Vector DB Integration

The parser pipeline should reuse the existing code embedder for semantic vectors rather than duplicating embedding logic in `ingest.py`.

Plan:

1. `pipeline.py` computes or requests embeddings for:
   - `CodeFile` summaries/content using the existing code embedder path.
   - `CodeSymbol` signatures and compact semantic text.
2. `persist.py` includes embedding vectors in statement/batch DTOs only as data.
3. `ingest.py` validates dimensions and writes embedding properties.
4. `schema/agent_memory_schema.cypher` owns vector indexes:
   - `idx_codefile_emb` on `CodeFile.embedding`.
   - `idx_symbol_emb` on `CodeSymbol.embedding`.
5. If the existing `CodeEmbedService.index_single_file` remains responsible for `CodeFile` embedding/upsert, parser ingest must coordinate with it through a public service API, not by duplicating DB writes outside `ingest.py`.

Open integration issue: `CodeEmbedService.upsert_code_file` currently writes directly to the DB. For this parser task, either:

- Refactor CodeFile parser ingest to route DB execution through `ingest.py`, while preserving the service as the embedding/content producer; or
- Keep legacy `CodeEmbedService` writes outside parser ingest temporarily, but document that parser-owned symbol/file graph writes still go only through `ingest.py`.

Preferred end state: all parser-triggered `CodeFile`, `CodeSymbol`, and code graph relationship writes go through `ingest.py`.

## MCP Tool Plan

Add parser tools as normal FastMCP tools using the repository's existing registration style.

Tool behavior:

- `parser_health`
  - Reports supported languages, asset paths, binary/query checksum status, loaded cache sizes, runtime dependency availability, and default limits.
- `parse_file`
  - Parses one file and returns parse status, root node type, language key, duration, and limit warnings.
  - Does not persist.
- `extract_code_symbols`
  - Parses and extracts one file, returning bounded symbol/edge summaries.
  - Does not persist.
- `index_code_symbols`
  - Parses, extracts, resolves, and persists one file into Ladybug.
- `index_code_tree`
  - Indexes a bounded include/exclude set under a root.
  - Must expose limits and return partial results if limits are reached.

All tools must return structured errors instead of raising raw Tree-sitter exceptions to clients.

## Integration Plan

### Phase 1: Foundation and Safety

- Add Tree-sitter Python runtime dependency.
- Implement asset discovery for the authoritative grammar layout.
- Implement checksum validation.
- Implement runtime safety limits.
- Implement parse-only API.
- Add parse smoke tests for every supported grammar binary.
- Add repeated parse tests that assert no obvious file descriptor, thread, or memory growth.

### Phase 2: Universal Query Extraction

- Implement DTOs and base extractor interface.
- Implement `ScmExtractor` for `queries/{language}.scm`.
- Implement generic shallow extraction for simple/config grammars.
- Add fixture tests for all supported language keys.

### Phase 3: Custom Extractors and Anonymous Symbols

- Implement custom Python, Go, TypeScript, TSX, Cypher, and SQL extractors.
- Implement anonymous-symbol extraction for Python, Go, and TypeScript.
- Unit test extracted node and edge counts against compact fixtures.
- Test that noisy literals, comments, punctuation, and local identifier spam are excluded.

### Phase 4: Resolvers

- Implement scope tree builder shared by code extractors.
- Implement import/module resolvers.
- Implement call resolvers.
- Implement anonymous-symbol resolvers for Python, Go, and TypeScript.
- Implement inheritance/type resolvers.
- Implement SQL/Cypher lineage resolvers.
- Add confidence scoring to `RESOLVES_TO`.

### Phase 5: Ladybug Persistence

- Add schema migration for `CodeSymbol.line_start` and `line_end`.
- Reconcile `CodeFile.embedding` and `CodeSymbol.embedding` dimensions with the configured code embedding model.
- Add/load required Ladybug extensions in schema/init: `vector`, `llm`, and `algo`.
- Add code graph relationship tables.
- Implement `persist.py` as a pure Cypher statement/batch builder.
- Implement `ingest.py` as the single DB execution boundary.
- Add explicit transaction, retry, rollback, and structured partial failure handling.
- Wire parser output into `CodeEmbedService.index_single_file` behind a feature flag only after standalone parser tools are stable.

### Phase 6: MCP and Dashboard Visibility

- Add parser MCP tools.
- Add parser status and code graph edges to dashboard visibility.
- Add metrics:
  - parse duration
  - captures per file
  - visited nodes per file
  - extracted nodes per file
  - extracted edges per file
  - resolver hit rate
  - limit hits
  - persistence batch size

## Test Plan

Unit tests:

- Grammar asset discovery for every supported language key.
- Literal `go.mod` and `go.sum` directory/query mapping.
- Parser loading for each `.so` file.
- Query loading for each `queries/{language}.scm` file.
- Parse-only smoke tests for representative fixture files.
- Extractor output for language fixtures.
- Anonymous-symbol extraction for Python, Go, and TypeScript.
- Resolver behavior for imports, calls, inheritance, async/await, goroutines, deferred calls, callbacks, SQL aliases, and Cypher aliases.
- Limit handling for file size, parse timeout, capture count, node count, symbol count, and edge count.

Integration tests:

- Index a small mixed-language fixture project.
- Verify `CodeFile`, `CodeSymbol`, and relationship rows are created.
- Verify vector indexes exist for `CodeFile` and `CodeSymbol`.
- Verify embedding vector dimensions match schema dimensions.
- Re-index after editing one fixture file and verify stale symbols are cleaned or archived.
- Verify MCP tools return structured results and structured errors.
- Verify no MCP tool imports `persist.py` or `ingest.py` directly.
- Verify `pipeline.py` does not execute DB queries directly.
- Verify only `ingest.py` imports/uses Ladybug connection execution for parser-owned writes.

Safety tests:

- Repeated parse/extract/index loop does not grow parser caches beyond configured bounds.
- No extra OS processes are created.
- No unmanaged threads remain after tool calls.
- File descriptors are stable across repeated calls.
- Large or pathological inputs terminate with limit-hit results.

DB verification:

- Query symbols by file.
- Query anonymous symbols by parent scope.
- Query callers/callees.
- Query imports.
- Query SQL table/column lineage.
- Query Cypher labels/relationship types used by schema and app queries.
- Query vector indexes for `CodeFile` and `CodeSymbol`.
- Project code graph relationships and run SCC for dependency-cycle detection.

## Open Decisions

1. Exact Tree-sitter Python binding package and version to use.
2. Whether parser instances are per-call or thread-local pooled after benchmarking.
3. Final default limits for file size, parse time, capture count, node visits, symbols, and edges.
4. Whether external modules/packages should become `CodeSymbol(kind="module")` records or a future `ExternalModule` table. Recommendation: use `CodeSymbol(kind="module")` initially.
5. Whether JavaScript gets TypeScript-style custom extraction in this task. Recommendation: keep this task focused on Python, Go, TypeScript/TSX, Cypher, SQL, and use universal extraction for JavaScript initially.
6. Whether automatic parser indexing should run during `CodeEmbedService.ensure_code_index`. Recommendation: explicit MCP tool and feature flag first, automatic later.
7. **BLOCKER**: Refactor `CodeEmbedService.upsert_code_file` so all parser-triggered `CodeFile`, `CodeSymbol`, and code graph relationship writes route through `ingest.py`. The preferred end state in the "Code Embedder / Vector DB Integration" section mandates this consolidation. Leaving `CodeEmbedService.upsert_code_file` outside `ingest.py` creates two concurrent write paths to the same tables with different transaction models and will cause data consistency issues. **This must be resolved before Phase 5 implementation begins.**
8. Whether to use the existing Python/Ollama embedding service only, or add an optional Ladybug `CREATE_EMBEDDING` repair path through the `llm` extension.
9. **BLOCKER**: Confirm and document the active Ollama code embedding model output dimension before Phase 5 schema migration. The embedding dimension must be declared in the project `.env` file (e.g., `OLLAMA_CODE_EMBED_DIM=768`) and reconciled with the schema columns `CodeFile.embedding` and `CodeSymbol.embedding` before vector index creation. Mismatched dimensions at migration time will create unusable vector indexes. Verify dimension with `OLLAMA_CODE_EMBED_MODEL` output before writing the schema.

## Initial Checklist

- [ ] Add Tree-sitter runtime dependency.
- [ ] Implement grammar asset discovery for `data/tree-sitter/grammar/{language}`.
- [ ] Validate every `.so`, `manifest.json`, `node-types.json`, and `queries/{language}.scm`.
- [ ] Implement runtime safety limits and cache policy.
- [ ] Implement parser loader and parse-only smoke tests.
- [ ] Implement universal SCM extractor.
- [ ] Implement custom Python, Go, TypeScript, TSX, Cypher, and SQL extractors.
- [ ] Implement anonymous-symbol extraction for Go, Python, and TypeScript.
- [ ] Implement resolvers, including anonymous-symbol resolvers.
- [ ] Add schema migration for `CodeSymbol` source spans.
- [ ] Update `schema/agent_memory_schema.cypher` for required parser relationships.
- [ ] Update `schema/agent_memory_schema.cypher` / DB init to install/load `vector`, `llm`, and `algo`.
- [ ] **PRE-CONDITION for Phase 5**: Confirm active `OLLAMA_CODE_EMBED_MODEL` output dimension by querying the model; update `.env` with `OLLAMA_CODE_EMBED_DIM` if needed.
- [ ] Reconcile code embedding dimensions in schema with `.env` and active Ollama model output (migrate `CodeFile.embedding` and `CodeSymbol.embedding` from `FLOAT[1536]` to correct dimension).
- [ ] Add code graph relationship tables.
- [ ] Implement `persist.py` as pure DTO -> Cypher statement/batch generation.
- [ ] Implement `ingest.py` as the single Ladybug DB execution boundary.
- [ ] Add explicit transaction, rollback, retry, stale cleanup, and structured `PersistenceResult` handling in `ingest.py`.
- [ ] **BLOCKER**: Refactor `CodeEmbedService.upsert_code_file` so all parser-triggered `CodeFile` writes route through `ingest.py`. Do not proceed with Phase 5 until all code DB writes are consolidated.
- [ ] Expose parser functionality as MCP tools.
- [ ] Wire parser indexing into code indexing behind a feature flag.
- [ ] Add dashboard/tool visibility.
- [ ] Add leak, thread, process, and bounded-memory safety tests.

## Reference Links

- Ladybug schema file: `schema/agent_memory_schema.cypher`
- Ladybug vector extension: https://docs.ladybugdb.com/extensions/vector/
- Ladybug LLM extension: https://docs.ladybugdb.com/extensions/llm/
- Ladybug SCC / algo extension: https://docs.ladybugdb.com/extensions/algo/scc/
- Ladybug algo extension overview: https://docs.ladybugdb.com/extensions/algo/
- Ollama embedding models: https://ollama.com/blog/embedding-models
