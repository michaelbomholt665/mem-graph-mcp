Great question — this is about building a meaningful **code graph** from Tree-sitter ASTs, where you want semantic signal, not syntax noise.

Here's a breakdown by language of the **important nodes** and the **edges** you'd want in an OpenCypher graph:

---

## Universal Node Types (all 3 languages)

| Node Label | Tree-sitter node type | What it captures |
|---|---|---|
| `File` | `source_file` / `module` | Top-level file |
| `Function` | `function_definition`, `function_declaration` | Named functions |
| `Class` | `class_definition`, `class_declaration` | Class declarations |
| `Method` | `method_definition` | Methods on classes |
| `Parameter` | `parameter`, `required_parameter` | Function params |
| `Import` | `import_statement`, `import_from_statement` | Module imports |
| `Call` | `call`, `call_expression` | Function/method calls |
| `Variable` | `assignment`, `variable_declarator` | Variable bindings |
| `Return` | `return_statement` | Return nodes |
| `TypeAnnotation` | `type_annotation`, `type_alias_declaration` | Type info |

---

## Language-Specific Nodes

### 🐍 Python
| Node Label | Tree-sitter type |
|---|---|
| `Decorator` | `decorator` |
| `Lambda` | `lambda` |
| `Comprehension` | `list_comprehension`, `dict_comprehension`, `generator_expression` |
| `WithStatement` | `with_statement` |
| `TryExcept` | `try_statement`, `except_clause` |
| `GlobalVar` | `global_statement` |

### 🐹 Go
| Node Label | Tree-sitter type |
|---|---|
| `Interface` | `interface_type` |
| `Struct` | `struct_type` |
| `Goroutine` | `go_statement` |
| `Channel` | `channel_type` |
| `DeferStatement` | `defer_statement` |
| `Package` | `package_clause` |
| `Receiver` | `parameter_list` on a method (the receiver) |

### 🟦 TypeScript / TSX
| Node Label | Tree-sitter type |
|---|---|
| `Interface` | `interface_declaration` |
| `Enum` | `enum_declaration` |
| `TypeAlias` | `type_alias_declaration` |
| `ArrowFunction` | `arrow_function` |
| `JSXElement` | `jsx_element`, `jsx_self_closing_element` |
| `JSXAttribute` | `jsx_attribute` |
| `Decorator` | `decorator` |
| `GenericType` | `type_parameters` |
| `ExportDecl` | `export_statement` |

---

## Edge Types (OpenCypher relationships)

These are the **relationships** that give a code graph its analytical power:

```cypher
// Structural containment
(File)-[:CONTAINS]->(Function|Class|Interface)
(Class)-[:HAS_METHOD]->(Method)
(Class)-[:HAS_FIELD]->(Variable)
(Function|Method)-[:HAS_PARAMETER]->(Parameter)

// Inheritance / implementation
(Class)-[:EXTENDS]->(Class)
(Class)-[:IMPLEMENTS]->(Interface)      // Go, TS
(Interface)-[:EXTENDS]->(Interface)    // TS

// Call graph
(Function|Method)-[:CALLS]->(Call)
(Call)-[:RESOLVES_TO]->(Function|Method)   // after resolution

// Data flow
(Function|Method)-[:ASSIGNS]->(Variable)
(Variable)-[:USED_IN]->(Function|Method)
(Function|Method)-[:RETURNS]->(TypeAnnotation)

// Import graph
(File)-[:IMPORTS]->(File|ExternalModule)
(Import)-[:REFERENCES]->(Function|Class|Variable)

// Type graph
(Variable|Parameter)-[:HAS_TYPE]->(TypeAnnotation)
(Function|Method)-[:RETURNS_TYPE]->(TypeAnnotation)
(TypeAlias|Interface)-[:COMPOSED_OF]->(TypeAnnotation)  // TS

// TSX-specific
(JSXElement)-[:RENDERS]->(JSXElement)
(JSXElement)-[:USES_COMPONENT]->(Function|Class)
(JSXElement)-[:HAS_PROP]->(JSXAttribute)

// Go-specific
(Function)-[:HAS_RECEIVER]->(Struct)
(Goroutine)-[:SPAWNS]->(Function)
(Function)-[:DEFERS]->(Function)
```

---

## Properties to store on nodes

```cypher
// Function / Method
{ name, start_line, end_line, is_async, is_exported, visibility }

// Class / Interface / Struct
{ name, start_line, is_abstract, is_exported }

// Call
{ name, start_line, is_method_call, receiver_name }

// Variable
{ name, start_line, is_const, scope }

// Import
{ module_path, alias, is_relative }
```

---

## What to **skip**

These add noise without semantic value:
- `comment`, `block_comment`
- `string`, `number`, `boolean` literals (unless doing data-flow analysis)
- Punctuation/operator nodes (`{`, `}`, `,`, `;`)
- `escape_sequence`
- `ERROR` recovery nodes (unless building a linter)
- Whitespace/newline nodes

---

## Query example (find all callers of a function)

```cypher
MATCH (caller:Function)-[:CALLS]->(c:Call)-[:RESOLVES_TO]->(f:Function {name: "processOrder"})
RETURN caller.name, caller.start_line
```

---

The most **high-value subgraph** for most use cases (code search, impact analysis, docs) is:
**`CONTAINS` + `CALLS` + `RESOLVES_TO` + `IMPORTS` + `EXTENDS/IMPLEMENTS`** — those five edge types alone give you a very rich navigable graph.

Good catch — async/await is semantically important and worth modeling explicitly. Here's the full breakdown:

---

## Tree-sitter Nodes for Async/Await

### 🐍 Python
| Node Label | Tree-sitter type | Notes |
|---|---|---|
| `AsyncFunction` | `function_definition` with `async` child | The `async` keyword is a child token |
| `AwaitExpression` | `await` | Inside async functions |
| `AsyncFor` | `for_statement` with `async` child | `async for x in ...` |
| `AsyncWith` | `with_statement` with `async` child | `async with ...` |

Detection in Python: the `async` keyword is a **named child** of the parent node, not a separate node type, so you need:
```python
node.type == "function_definition" and node.child(0).type == "async"
```

### 🐹 Go
Go doesn't have async/await — it uses **goroutines + channels**. The equivalent modeling:

| Node Label | Tree-sitter type | Async analog |
|---|---|---|
| `Goroutine` | `go_statement` | "fire and forget" async call |
| `Channel` | `channel_type` | typed async communication |
| `SelectStatement` | `select_statement` | await-on-multiple-channels |
| `SendStatement` | `send_statement` | `ch <- value` |
| `ReceiveExpr` | `unary_expression` with `<-` | `<-ch` (blocking receive) |

### 🟦 TypeScript / TSX
| Node Label | Tree-sitter type | Notes |
|---|---|---|
| `AsyncFunction` | `function_declaration` / `arrow_function` / `method_definition` with `async` | `async` is a named field |
| `AwaitExpression` | `await_expression` | Explicit node type ✅ |
| `PromiseType` | `generic_type` where name = `Promise` | `Promise<T>` in return types |

TypeScript is the cleanest — `await_expression` is a **first-class node type**.

---

## Additional Graph Nodes

```cypher
(AsyncFunction)   // function that has async modifier
(AwaitExpression) // a specific await call site
(PromiseType)     // return type annotation Promise<T>
```

---

## Additional Edge Types

```cypher
// Mark async boundary
(Function)-[:IS_ASYNC]->()               // or just a property: {is_async: true}

// Await edges — where is execution suspended?
(AsyncFunction)-[:AWAITS]->(AwaitExpression)
(AwaitExpression)-[:AWAITS_CALL]->(Call)
(Call)-[:RESOLVES_TO]->(AsyncFunction)   // callee is also async

// Promise chains (TS/JS)
(Call)-[:CHAINS]->(Call)                 // .then().catch() chains
(Function)-[:RETURNS_PROMISE]->(PromiseType)

// Go concurrency
(Goroutine)-[:SPAWNS]->(Function)
(Function)-[:SENDS_TO]->(Channel)
(Function)-[:RECEIVES_FROM]->(Channel)
(SelectStatement)-[:LISTENS_ON]->(Channel)
```

---

## Properties to add

```cypher
// On Function/Method nodes — extend existing
{
  is_async: true,
  returns_promise: true,    // TS: inferred or annotated
  has_await: true           // contains at least one await expression
}

// On AwaitExpression
{
  start_line: 42,
  is_top_level: false       // top-level await (ES modules)
}

// On Call (when calling an async fn)
{
  is_awaited: true,         // wrapped in await_expression
  is_fire_and_forget: false // called without await — potential bug!
}
```

---

## Why `is_fire_and_forget` matters

This is a **high-value derived edge** — a call to an async function that is **not awaited**:

```cypher
// Find unawaited async calls — common bug pattern
MATCH (caller:Function)-[:CALLS]->(c:Call)-[:RESOLVES_TO]->(f:Function {is_async: true})
WHERE c.is_awaited = false
RETURN caller.name, c.name, c.start_line
```

---

## Async Propagation Chain Query

```cypher
// Find all async functions transitively called from an entry point
MATCH path = (entry:Function {name: "handleRequest"})-[:CALLS*..10]->(c:Call)-[:RESOLVES_TO]->(f:Function {is_async: true})
RETURN f.name, length(path) as depth
ORDER BY depth
```

---

## Summary of what to capture

| Concept | Python | TypeScript | Go |
|---|---|---|---|
| Async declaration | `async` child token on fn | `async` field on fn | `go_statement` |
| Suspension point | `await` node | `await_expression` node | `<-` receive / `select` |
| Async type | — | `Promise<T>` generic | `chan T` |
| Fire-and-forget risk | unawaited `async` call | unawaited `async` call | every `go` statement |
| Multi-await | `asyncio.gather` call | `Promise.all` call | `select` statement |

The most semantically rich edge to add is `(AwaitExpression)-[:AWAITS_CALL]->(Call)-[:RESOLVES_TO]->(AsyncFunction)` — it lets you trace the full async call chain and find broken async boundaries.

Yes! `node-types.json` contains enough structural information to bootstrap `.scm` query files. It won't give you 100% semantic meaning (it can't know *which* nodes matter for your use case), but it can generate **valid, complete** queries for all named node types and their fields.

---

## What `node-types.json` gives you

Each entry looks like:
```json
{
  "type": "function_definition",
  "named": true,
  "fields": {
    "name": { "types": [{ "type": "identifier", "named": true }] },
    "parameters": { "types": [{ "type": "parameters", "named": true }] },
    "body": { "types": [{ "type": "block", "named": true }] }
  },
  "children": { ... }
}
```

So you can derive:
- All valid node types (`type` field)
- Their named fields (`fields`)
- Whether they're named vs anonymous
- Child types

---

## The Script

```python
#!/usr/bin/env python3
"""
Generate Tree-sitter .scm query files from node-types.json
Usage: python gen_scm.py --lang python --node-types ./node-types.json --out ./queries/
"""

import json
import argparse
from pathlib import Path

# ── Nodes worth capturing per language ──────────────────────────────────────

IMPORTANT_NODES = {
    "python": {
        "function_definition", "async_function_definition", "class_definition",
        "decorated_definition", "call", "import_statement", "import_from_statement",
        "assignment", "return_statement", "await", "lambda", "decorator",
        "with_statement", "try_statement", "for_statement", "parameters",
        "identifier", "attribute",
    },
    "typescript": {
        "function_declaration", "method_definition", "class_declaration",
        "arrow_function", "call_expression", "await_expression",
        "import_statement", "export_statement", "interface_declaration",
        "type_alias_declaration", "enum_declaration", "variable_declarator",
        "return_statement", "jsx_element", "jsx_self_closing_element",
        "jsx_attribute", "decorator", "type_annotation",
    },
    "go": {
        "function_declaration", "method_declaration", "type_declaration",
        "struct_type", "interface_type", "call_expression", "go_statement",
        "defer_statement", "send_statement", "receive_statement",
        "import_declaration", "package_clause", "channel_type",
        "select_statement", "short_var_declaration", "return_statement",
    },
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def load_node_types(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    return {entry["type"]: entry for entry in data if entry.get("named")}

def get_fields(entry: dict) -> list[str]:
    return list(entry.get("fields", {}).keys())

def get_child_types(entry: dict) -> list[str]:
    children = entry.get("children", {}).get("types", [])
    return [c["type"] for c in children if c.get("named")]

# ── SCM generators ───────────────────────────────────────────────────────────

def gen_capture_query(node_type: str, entry: dict, tag: str | None = None) -> str:
    """Generate a basic capture query for a node type."""
    cap = tag or node_type.replace("_", "-")
    fields = get_fields(entry)
    lines = [f"({node_type}"]
    for field in fields:
        field_types = entry["fields"][field].get("types", [])
        named = [t["type"] for t in field_types if t.get("named")]
        if named:
            # Use first valid type as example; real nodes may have multiple
            lines.append(f"  {field}: (_) @{cap}.{field}")
    lines.append(f") @{cap}")
    return "\n".join(lines)

def gen_highlights_scm(node_types: dict, important: set) -> str:
    """Generate highlights.scm — captures all important nodes."""
    sections = ["; Auto-generated highlights.scm\n"]
    for ntype, entry in node_types.items():
        if ntype not in important:
            continue
        sections.append(f"; ── {ntype} ──")
        sections.append(gen_capture_query(ntype, entry))
        sections.append("")
    return "\n".join(sections)

def gen_tags_scm(node_types: dict, important: set) -> str:
    """Generate tags.scm — for symbol extraction (used by nvim, etc.)."""
    lines = ["; Auto-generated tags.scm\n"]
    tag_nodes = {
        "function_definition", "function_declaration", "method_definition",
        "method_declaration", "class_definition", "class_declaration",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
    }
    for ntype, entry in node_types.items():
        if ntype not in important or ntype not in tag_nodes:
            continue
        fields = get_fields(entry)
        if "name" in fields:
            lines.append(f"({ntype} name: (identifier) @name) @definition.{ntype.replace('_definition','').replace('_declaration','')}")
    return "\n".join(lines)

def gen_locals_scm(node_types: dict, important: set) -> str:
    """Generate locals.scm — scope/definition/reference markers."""
    lines = ["; Auto-generated locals.scm\n"]
    scope_nodes = {
        "function_definition", "function_declaration", "method_definition",
        "method_declaration", "class_definition", "class_declaration",
        "block", "module",
    }
    for ntype in node_types:
        if ntype in scope_nodes and ntype in important:
            lines.append(f"({ntype}) @local.scope")

    lines.append("")
    lines.append("; Definitions")
    def_nodes = {"assignment", "variable_declarator", "short_var_declaration", "parameter"}
    for ntype, entry in node_types.items():
        if ntype in def_nodes:
            if "name" in get_fields(entry):
                lines.append(f"({ntype} name: (identifier) @local.definition)")

    lines.append("")
    lines.append("; References")
    lines.append("(identifier) @local.reference")

    return "\n".join(lines)

# ── Verification ─────────────────────────────────────────────────────────────

def verify_scm(scm_content: str, node_types: dict) -> list[str]:
    """
    Basic static verification: check all node types referenced in
    the .scm exist in node-types.json.
    Returns list of warnings.
    """
    import re
    warnings = []
    # Extract node type names from patterns like (node_type ...)
    found = re.findall(r'\(([a-z_][a-z0-9_]*)', scm_content)
    for node in set(found):
        if node not in node_types and not node.startswith("_"):
            warnings.append(f"  ⚠ Unknown node type: '{node}'")
    return warnings

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", required=True, choices=IMPORTANT_NODES.keys())
    parser.add_argument("--node-types", required=True)
    parser.add_argument("--out", default="./queries")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    node_types = load_node_types(args.node_types)
    important = IMPORTANT_NODES[args.lang]

    print(f"Loaded {len(node_types)} named node types for {args.lang}")
    print(f"Targeting {len(important)} important nodes\n")

    outputs = {
        "highlights.scm": gen_highlights_scm(node_types, important),
        "tags.scm":       gen_tags_scm(node_types, important),
        "locals.scm":     gen_locals_scm(node_types, important),
    }

    for filename, content in outputs.items():
        path = out_dir / filename
        path.write_text(content)
        warnings = verify_scm(content, node_types)
        status = "✅" if not warnings else "⚠️ "
        print(f"{status} {filename} ({len(content.splitlines())} lines)")
        for w in warnings:
            print(w)

    print(f"\nDone → {out_dir}/")

if __name__ == "__main__":
    main()
```

---

## Usage

```bash
# Generate for Python
python gen_scm.py --lang python \
  --node-types ./tree-sitter-python/src/node-types.json \
  --out ./queries/python/

# Generate for TypeScript
python gen_scm.py --lang typescript \
  --node-types ./tree-sitter-typescript/typescript/src/node-types.json \
  --out ./queries/typescript/

# Generate for Go
python gen_scm.py --lang go \
  --node-types ./tree-sitter-go/src/node-types.json \
  --out ./queries/go/
```

---

## What it generates

```
queries/python/
  highlights.scm   ← all important nodes captured with field captures
  tags.scm         ← symbol definitions (functions, classes, etc.)
  locals.scm       ← scope / definition / reference markers
```

---

## Limitations to be aware of

| Limitation | Why | Mitigation |
|---|---|---|
| No semantic field selection | `node-types.json` lists all fields, not which ones are meaningful | The `IMPORTANT_NODES` set acts as a filter |
| No predicate generation | `#eq?`, `#match?` etc. can't be inferred from structure | Add manually for things like `async` keyword detection |
| Field types may be unions | A field can accept multiple node types — the script uses `(_)` wildcard | Fine for capture, refine for strict matching |
| `async` in Python/Go isn't a node | It's a keyword child token, not a named node | Needs a manual `#match?` predicate |

---

## Extending for async detection

Since `async` is a token-level thing in Python and Go, add this post-generation:

```scheme
; append to highlights.scm manually or via a patch step
(function_definition
  "async" @keyword.async
  name: (identifier) @async-function.name) @async-function

(await
  (call (identifier) @await.callee)) @await-expression
```

The script gives you the 80% — the async/keyword edge cases are the 20% you patch by hand or add as a separate `patches/` layer on top of the generated files.

Great addition — Cypher and SQL are both query languages so the graph model is about **query structure** rather than code structure. Here's the minimal set:

---

## 🔵 Cypher (OpenCypher / Neo4j)

### Important Nodes

| Node Label | Tree-sitter type | What it captures |
|---|---|---|
| `Query` | `query` | Top-level query |
| `Match` | `match_clause` | MATCH clause |
| `Where` | `where_clause` | WHERE predicate |
| `Return` | `return_clause` | RETURN clause |
| `With` | `with_clause` | WITH (pipeline step) |
| `Create` | `create_clause` | CREATE clause |
| `Merge` | `merge_clause` | MERGE clause |
| `Delete` | `delete_clause` | DELETE / DETACH DELETE |
| `Set` | `set_clause` | SET property |
| `NodePattern` | `node_pattern` | `(n:Label)` |
| `RelPattern` | `relationship_pattern` | `-[r:TYPE]->` |
| `PathPattern` | `path_pattern` | Full path expression |
| `Label` | `node_label` | `:Person`, `:Order` |
| `RelType` | `relationship_type` | `:KNOWS`, `:ORDERS` |
| `Property` | `property_key_name` | `n.name`, `r.since` |
| `Variable` | `variable` | `n`, `r`, `p` |
| `Parameter` | `parameter` | `$param` |
| `FunctionCall` | `function_invocation` | `count()`, `collect()` |
| `UnwindClause` | `unwind_clause` | UNWIND lists |
| `OrderBy` | `order_clause` | ORDER BY |
| `Limit` | `limit_clause` | LIMIT |
| `Skip` | `skip_clause` | SKIP |
| `Subquery` | `call_clause` | CALL { ... } subquery |

### Important Edges

```cypher
(Query)-[:HAS_CLAUSE]->(Match|Create|Merge|Return|With|Delete|Set)
(Match)-[:HAS_PATTERN]->(PathPattern|NodePattern|RelPattern)
(NodePattern)-[:HAS_LABEL]->(Label)
(NodePattern)-[:BOUND_TO]->(Variable)
(RelPattern)-[:HAS_TYPE]->(RelType)
(RelPattern)-[:BOUND_TO]->(Variable)
(RelPattern)-[:FROM]->(NodePattern)
(RelPattern)-[:TO]->(NodePattern)
(Where)-[:FILTERS]->(NodePattern|RelPattern|Variable)
(Return)-[:PROJECTS]->(Variable|Property|FunctionCall)
(With)-[:PASSES]->(Variable|Property|FunctionCall)
(FunctionCall)-[:AGGREGATES]->(Variable)   // count, collect, sum...
(Query)-[:USES_PARAM]->(Parameter)
(Subquery)-[:CONTAINS]->(Query)
```

### Properties

```cypher
// NodePattern
{ alias: "n", labels: ["Person"], start_line: 3 }

// RelPattern
{ alias: "r", type: "KNOWS", direction: "outgoing"|"incoming"|"undirected", min_hops: 1, max_hops: null }

// FunctionCall
{ name: "count", is_aggregation: true, is_distinct: false }

// Query
{ type: "read"|"write"|"read_write", has_subquery: false }
```

---

## 🟡 SQL — DuckDB + PostgreSQL 18

They share ~90% grammar. I'll mark divergences explicitly.

### Important Nodes

| Node Label | Tree-sitter type | Notes |
|---|---|---|
| `Statement` | `statement` | Top-level |
| `Select` | `select_statement` / `select_clause` | SELECT |
| `From` | `from_clause` | FROM |
| `Join` | `join_clause` | All JOIN types |
| `Where` | `where_clause` | WHERE |
| `GroupBy` | `group_by_clause` | GROUP BY |
| `Having` | `having_clause` | HAVING |
| `OrderBy` | `order_by_clause` | ORDER BY |
| `Limit` | `limit_clause` | LIMIT / FETCH |
| `With` | `with_clause` | CTE |
| `CTE` | `cte_definition` | Individual CTE |
| `Insert` | `insert_statement` | INSERT INTO |
| `Update` | `update_statement` | UPDATE |
| `Delete` | `delete_statement` | DELETE |
| `CreateTable` | `create_table_statement` | DDL |
| `CreateIndex` | `create_index_statement` | DDL |
| `TableRef` | `table_reference` / `relation` | Table name in FROM/JOIN |
| `ColumnRef` | `column_reference` | `t.col`, `col` |
| `Alias` | `alias` | `AS x` |
| `Subquery` | `subquery` / `select_subexpression` | Nested SELECT |
| `FunctionCall` | `function_call` | `count()`, `sum()` |
| `WindowFunction` | `window_function` | `OVER (PARTITION BY ...)` |
| `Window` | `window_definition` | PARTITION BY / ORDER BY inside OVER |
| `SetOperation` | `union` / `intersect` / `except` | Set ops |
| `Parameter` | `parameter` | `$1`, `?`, named params |
| `TypeCast` | `type_cast` | `::int`, `CAST(x AS ...)` |

#### DuckDB-specific
| Node Label | Tree-sitter type | Notes |
|---|---|---|
| `PivotClause` | `pivot_clause` | PIVOT / UNPIVOT |
| `SampleClause` | `tablesample_clause` | USING SAMPLE |
| `LambdaExpr` | `lambda_function` | `x -> x + 1` |
| `ListComprehension` | `list_comprehension` | `[x FOR x IN ...]` |
| `Positional` | `positional_reference` | `$1` style |

#### PostgreSQL 18-specific
| Node Label | Tree-sitter type | Notes |
|---|---|---|
| `ReturningClause` | `returning_clause` | INSERT/UPDATE ... RETURNING |
| `OnConflict` | `on_conflict_clause` | UPSERT |
| `DoBlock` | `do_statement` | Anonymous PL/pgSQL |
| `CreateFunction` | `create_function_statement` | Stored proc/function |
| `MaterializedCTE` | `with_clause` + `MATERIALIZED` keyword | CTE hint |
| `MergeStatement` | `merge_statement` | SQL:2003 MERGE (pg15+) |
| `JsonTable` | `json_table` | pg16+ JSON_TABLE |

---

### Important Edges

```cypher
// Query structure
(Statement)-[:HAS_CTE]->(CTE)
(CTE)-[:DEFINES]->(Subquery)
(Statement)-[:HAS_SELECT]->(Select)
(Statement)-[:HAS_FROM]->(From)
(From)-[:READS]->(TableRef|Subquery)
(Statement)-[:HAS_JOIN]->(Join)
(Join)-[:JOINS]->(TableRef|Subquery)
(Join)-[:ON]->(ColumnRef)           // join condition columns
(Statement)-[:HAS_WHERE]->(Where)
(Where)-[:FILTERS_ON]->(ColumnRef)
(Statement)-[:HAS_GROUPBY]->(GroupBy)
(GroupBy)-[:GROUPS_BY]->(ColumnRef)
(Statement)-[:HAS_HAVING]->(Having)
(Statement)-[:HAS_ORDERBY]->(OrderBy)
(OrderBy)-[:ORDERS_BY]->(ColumnRef)

// Column / table lineage
(Select)-[:PROJECTS]->(ColumnRef|FunctionCall|Subquery)
(ColumnRef)-[:FROM_TABLE]->(TableRef)    // after resolution
(Alias)-[:ALIASES]->(TableRef|Subquery|ColumnRef|FunctionCall)

// Functions & windows
(FunctionCall)-[:AGGREGATES]->(ColumnRef)
(WindowFunction)-[:OVER]->(Window)
(Window)-[:PARTITIONS_BY]->(ColumnRef)
(Window)-[:ORDERS_BY]->(ColumnRef)

// Nesting
(Subquery)-[:CONTAINS]->(Statement)
(SetOperation)-[:LEFT]->(Statement)
(SetOperation)-[:RIGHT]->(Statement)

// DML
(Insert)-[:INTO]->(TableRef)
(Insert)-[:FROM_SELECT]->(Statement)
(Update)-[:UPDATES]->(TableRef)
(Update)-[:SETS]->(ColumnRef)
(Delete)-[:FROM]->(TableRef)

// PostgreSQL extras
(Statement)-[:RETURNS]->(ColumnRef)     // RETURNING clause
(CreateFunction)-[:CONTAINS]->(Statement)
```

### Properties

```cypher
// TableRef
{ name: "orders", schema: "public", alias: "o", is_cte: false, is_subquery: false }

// ColumnRef
{ name: "created_at", table_alias: "o", is_star: false, is_qualified: true }

// Join
{ type: "INNER"|"LEFT"|"RIGHT"|"FULL"|"CROSS", is_lateral: false }

// FunctionCall
{ name: "count", is_aggregate: true, is_window: false, is_distinct: false }

// Statement
{ type: "SELECT"|"INSERT"|"UPDATE"|"DELETE"|"DDL",
  has_cte: true, has_window: false, has_subquery: true,
  dialect: "duckdb"|"postgresql" }

// CTE
{ name: "ranked_orders", is_recursive: false, is_materialized: true }
```

---

## Updated `gen_scm.py` additions

Add these to `IMPORTANT_NODES`:

```python
IMPORTANT_NODES["cypher"] = {
    "query", "match_clause", "where_clause", "return_clause",
    "with_clause", "create_clause", "merge_clause", "delete_clause",
    "set_clause", "node_pattern", "relationship_pattern", "path_pattern",
    "node_label", "relationship_type", "property_key_name", "variable",
    "parameter", "function_invocation", "unwind_clause", "order_clause",
    "limit_clause", "skip_clause", "call_clause",
}

IMPORTANT_NODES["sql"] = {
    "statement", "select_statement", "from_clause", "join_clause",
    "where_clause", "group_by_clause", "having_clause", "order_by_clause",
    "limit_clause", "with_clause", "cte_definition", "insert_statement",
    "update_statement", "delete_statement", "create_table_statement",
    "table_reference", "column_reference", "alias", "subquery",
    "function_call", "window_function", "window_definition",
    "union", "intersect", "except", "parameter", "type_cast",
    # pg extras
    "returning_clause", "on_conflict_clause", "create_function_statement",
    "merge_statement",
    # duckdb extras
    "pivot_clause", "tablesample_clause", "lambda_function",
}
```

---

## Key difference from code grammars

The most important thing to track in query languages is **lineage** — where does each column/table reference come from? That means the highest-value edges are:

```
ColumnRef -[:FROM_TABLE]-> TableRef
TableRef  -[:ALIASES]->    Alias
Subquery  -[:CONTAINS]->   Statement
CTE       -[:DEFINES]->    Subquery
Select    -[:PROJECTS]->   ColumnRef
```

These five let you answer "what tables does this query touch?" and "what is the data lineage of this output column?" — which are the two killer queries for a SQL/Cypher graph.
