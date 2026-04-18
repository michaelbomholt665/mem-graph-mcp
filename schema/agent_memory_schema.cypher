// =============================================================================
// agent_memory_schema.cypher
// Agent Memory Storage System — Ladybug Graph Database
//
// Embedding dim: 1536  (OpenAI text-embedding-3-small / change to suit model)
// UUIDv7 strings used as primary keys for temporal ordering.
// All embeddable nodes carry a FLOAT[1536] embedding property for HNSW search.
// =============================================================================

// ---------------------------------------------------------------------------
// Extensions
// ---------------------------------------------------------------------------
INSTALL vector; LOAD vector;
INSTALL fts;    LOAD fts;


// =============================================================================
// SCHEMA META  (written once by init_db, validated on every subsequent startup)
// =============================================================================
CREATE NODE TABLE IF NOT EXISTS SchemaMeta (
    version        STRING PRIMARY KEY,  -- semver string, e.g. "1.0"
    embed_dim      INT64,               -- must match OLLAMA_EMBED_DIM at runtime
    initialized_at TIMESTAMP DEFAULT current_timestamp()
);


// =============================================================================
// NODE TABLES
// =============================================================================

// ---------------------------------------------------------------------------
// Agent — the AI agent instance (Opus, Sonnet, Codex, etc.)
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Agent (
    id          STRING PRIMARY KEY,   -- UUIDv7
    name        STRING,               -- e.g. "claude-opus-4-6", "codex-cli"
    role        STRING,               -- planner | coder | auditor | reviewer
    model       STRING,               -- raw model string
    last_run_at TIMESTAMP,
    status_metadata STRING,
    created_at  TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Project — top-level isolation boundary
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Project (
    id          STRING PRIMARY KEY,
    name        STRING,
    description STRING,
    status      STRING DEFAULT 'active',  -- active | paused | archived
    repo_path   STRING,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp(),
    updated_at  TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Backend — language / service boundary within a project
// e.g. "go-core", "python-analytics", "typescript-frontend"
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Backend (
    id          STRING PRIMARY KEY,
    name        STRING,
    language    STRING,               -- go | python | typescript | rust | …
    root_path   STRING,
    description STRING,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Task — unit of work tracked across sessions
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Task (
    id           STRING PRIMARY KEY,
    title        STRING,
    description  STRING,
    status       STRING DEFAULT 'open',   -- open | in_progress | blocked | done | cancelled
    priority     STRING DEFAULT 'normal', -- low | normal | high | critical
    audit_id     STRING,                  -- e.g. "002A" — matches violation lifecycle IDs
    phase        STRING,                  -- planning | red | green | refactor | audit
    embedding    FLOAT[1536],
    created_at   TIMESTAMP DEFAULT current_timestamp(),
    updated_at   TIMESTAMP DEFAULT current_timestamp(),
    completed_at TIMESTAMP
);

// ---------------------------------------------------------------------------
// Decision — architectural or implementation choice
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Decision (
    id           STRING PRIMARY KEY,
    title        STRING,
    rationale    STRING,
    alternatives STRING,              -- rejected options, free text
    status       STRING DEFAULT 'active',  -- active | superseded | reverted
    impact       STRING DEFAULT 'low',     -- low | medium | high | critical
    embedding    FLOAT[1536],
    created_at   TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Note — free-form observation, finding, or reminder
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Note (
    id         STRING PRIMARY KEY,
    kind       STRING DEFAULT 'general',  -- general | finding | warning | lesson | audit
    title      STRING,
    body       STRING,
    tags       STRING[],                  -- arbitrary tag list
    embedding  FLOAT[1536],
    created_at TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Violation — policy / smell / audit finding (feeds violation lifecycle)
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Violation (
    id          STRING PRIMARY KEY,
    audit_id    STRING,               -- e.g. "002A"
    rule        STRING,               -- CWE-252, SonarQube:S2093, custom:no-todo
    severity    STRING DEFAULT 'info', -- info | minor | major | critical | blocker
    file_path   STRING,
    line_start  INT64,
    line_end    INT64,
    description STRING,
    fingerprint STRING,               -- SHA-256 dedup key (first 16 hex chars)
    status      STRING DEFAULT 'open', -- open | recurrence | resolved | graduated
    embedding   FLOAT[1536],
    detected_at TIMESTAMP DEFAULT current_timestamp(),
    last_seen_at TIMESTAMP,
    resolved_at TIMESTAMP
);

// ---------------------------------------------------------------------------
// Conversation — a discrete agent session / turn boundary
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Conversation (
    id          STRING PRIMARY KEY,
    title       STRING,
    summary     STRING,
    summary_status STRING,
    model       STRING,
    turn_count  INT64 DEFAULT 0,
    embedding   FLOAT[1536],
    started_at  TIMESTAMP DEFAULT current_timestamp(),
    ended_at    TIMESTAMP
);

// ---------------------------------------------------------------------------
// Message — single turn within a conversation
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Message (
    id          STRING PRIMARY KEY,
    role        STRING,               -- user | assistant | system | tool
    content     STRING,
    tool_name   STRING,               -- populated when role=tool
    token_count INT64,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Memory — distilled, persistent fact extracted from conversations
// Analogous to the memory-bank entries in your SKILL system.
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Memory (
    id         STRING PRIMARY KEY,
    kind       STRING DEFAULT 'fact',  -- fact | preference | pattern | violation | architecture
    scope      STRING DEFAULT 'global', -- global | project | backend | task
    content    STRING,
    confidence FLOAT DEFAULT 1.0,
    embedding  FLOAT[1536],
    created_at TIMESTAMP DEFAULT current_timestamp(),
    updated_at TIMESTAMP DEFAULT current_timestamp(),
    expires_at TIMESTAMP              -- NULL = never expires
);

// ---------------------------------------------------------------------------
// CodeSymbol — symbol reference for traceability (ISR/Syntx integration)
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS CodeSymbol (
    id         STRING PRIMARY KEY,
    name       STRING,
    kind       STRING,                -- function | method | struct | interface | const | …
    file_path  STRING,
    language   STRING,
    signature  STRING,
    embedding  FLOAT[1536],
    indexed_at TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// CodeFile — file-level code artifact for semantic linking and explorer metadata
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS CodeFile (
    id         STRING PRIMARY KEY,
    path       STRING,
    name       STRING,
    language   STRING,
    size_bytes INT64,
    content_hash STRING,
    summary    STRING,
    embedding  FLOAT[1536],
    indexed_at TIMESTAMP DEFAULT current_timestamp(),
    updated_at TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// JinaIssue — external work item ingested from Jina for code traceability
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS JinaIssue (
    id          STRING PRIMARY KEY,
    issue_key   STRING,
    title       STRING,
    description STRING,
    status      STRING,
    assignee    STRING,
    url         STRING,
    source_hash STRING,
    embedding   FLOAT[1536],
    created_at  TIMESTAMP,
    synced_at   TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// EvalRun — persisted summary of an eval execution for regression tracking
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS EvalRun (
    id                STRING PRIMARY KEY,
    mode              STRING,
    label             STRING,
    trigger           STRING,
    logfire_run_id    STRING,
    total_suites      INT64,
    passed_suites     INT64,
    suite_pass_rate   DOUBLE,
    total_duration_ms DOUBLE,
    suite_names       STRING[],
    passed_suite_names STRING[],
    summary           STRING,
    report_path       STRING,
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    persisted_at      TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// DashboardConfig — persisted dashboard preferences per project/user surface
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS DashboardConfig (
    id              STRING PRIMARY KEY,
    project_id      STRING,
    pinned_projects STRING[],
    theme           STRING,
    filters_json    STRING,
    created_at      TIMESTAMP DEFAULT current_timestamp(),
    updated_at      TIMESTAMP DEFAULT current_timestamp()
);

// ---------------------------------------------------------------------------
// Tag — reusable label node for many-to-many tagging
// ---------------------------------------------------------------------------
CREATE NODE TABLE IF NOT EXISTS Tag (
    name STRING PRIMARY KEY
);


// =============================================================================
// RELATIONSHIP TABLES
// =============================================================================

// Project containment
CREATE REL TABLE IF NOT EXISTS HAS_BACKEND   (FROM Project  TO Backend,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_TASK      (FROM Project  TO Task,          assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_DECISION  (FROM Project  TO Decision,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_NOTE      (FROM Project  TO Note,          assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_VIOLATION (FROM Project  TO Violation,     assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_FILE      (FROM Project  TO CodeFile,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_JINA_ISSUE (FROM Project TO JinaIssue,     assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS HAS_EVAL_RUN  (FROM Project  TO EvalRun,       assigned_at TIMESTAMP DEFAULT current_timestamp());

// Backend containment
CREATE REL TABLE IF NOT EXISTS BACKEND_TASK      (FROM Backend TO Task,      assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS BACKEND_DECISION  (FROM Backend TO Decision,  assigned_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS BACKEND_SYMBOL    (FROM Backend TO CodeSymbol);
CREATE REL TABLE IF NOT EXISTS BACKEND_VIOLATION (FROM Backend TO Violation);

// Task relationships
CREATE REL TABLE IF NOT EXISTS TASK_BLOCKS    (FROM Task TO Task, reason STRING);
CREATE REL TABLE IF NOT EXISTS TASK_SPAWNS    (FROM Task TO Task, reason STRING);
CREATE REL TABLE IF NOT EXISTS TASK_DECISION  (FROM Task TO Decision);
CREATE REL TABLE IF NOT EXISTS TASK_VIOLATION (FROM Task TO Violation);
CREATE REL TABLE IF NOT EXISTS TASK_NOTE      (FROM Task TO Note);

// Decision relationships
CREATE REL TABLE IF NOT EXISTS SUPERSEDES     (FROM Decision TO Decision, reason STRING, superseded_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS DECISION_NOTE  (FROM Decision TO Note);

// Violation relationships
CREATE REL TABLE IF NOT EXISTS VIOLATION_RECURS (FROM Violation TO Violation, detected_at TIMESTAMP DEFAULT current_timestamp());

// Conversation / Message chain
CREATE REL TABLE IF NOT EXISTS PROJECT_CONVERSATION (FROM Project      TO Conversation);
CREATE REL TABLE IF NOT EXISTS AGENT_CONVERSATION   (FROM Agent        TO Conversation);
CREATE REL TABLE IF NOT EXISTS NEXT_MESSAGE         (FROM Message      TO Message,      turn_index INT64);
CREATE REL TABLE IF NOT EXISTS CONVERSATION_MESSAGE (FROM Conversation TO Message,      position   INT64);

// Memory linkage
CREATE REL TABLE IF NOT EXISTS MEMORY_SOURCE   (FROM Memory TO Conversation, extracted_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS PROJECT_MEMORY  (FROM Project  TO Memory);
CREATE REL TABLE IF NOT EXISTS BACKEND_MEMORY  (FROM Backend  TO Memory);
CREATE REL TABLE IF NOT EXISTS TASK_MEMORY     (FROM Task     TO Memory);
CREATE REL TABLE IF NOT EXISTS MEMORY_SUPERSEDES (FROM Memory TO Memory, reason STRING);

// Cross-cutting agent authorship
CREATE REL TABLE IF NOT EXISTS AUTHORED_BY (
    FROM Task      TO Agent,
    FROM Decision  TO Agent,
    FROM Note      TO Agent,
    FROM Violation TO Agent,
    FROM Memory    TO Agent,
    FROM Message   TO Agent,
    created_at TIMESTAMP DEFAULT current_timestamp()
);

// Symbol ↔ Task / Violation / Decision traceability
CREATE REL TABLE IF NOT EXISTS SYMBOL_TASK      (FROM CodeSymbol TO Task);
CREATE REL TABLE IF NOT EXISTS SYMBOL_VIOLATION (FROM CodeSymbol TO Violation);
CREATE REL TABLE IF NOT EXISTS SYMBOL_DECISION  (FROM CodeSymbol TO Decision);

// Jina ↔ code traceability
CREATE REL TABLE IF NOT EXISTS IMPLEMENTS (FROM JinaIssue TO CodeFile, score DOUBLE, snippet STRING, linked_at TIMESTAMP DEFAULT current_timestamp());
CREATE REL TABLE IF NOT EXISTS MENTIONS   (FROM JinaIssue TO CodeFile, score DOUBLE, snippet STRING, linked_at TIMESTAMP DEFAULT current_timestamp());

// Tagging (Note, Task, Memory, Violation share Tag nodes)
CREATE REL TABLE IF NOT EXISTS TAGGED (
    FROM Note      TO Tag,
    FROM Task      TO Tag,
    FROM Memory    TO Tag,
    FROM Violation TO Tag,
    FROM Decision  TO Tag
);


// =============================================================================
// VECTOR INDEXES  (HNSW, cosine similarity)
// =============================================================================

CALL CREATE_VECTOR_INDEX('Project',     'idx_project_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Backend',     'idx_backend_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Task',        'idx_task_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Decision',    'idx_decision_emb',   'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Note',        'idx_note_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Violation',   'idx_violation_emb',  'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Conversation','idx_conv_emb',       'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Message',     'idx_message_emb',    'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('Memory',      'idx_memory_emb',     'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('CodeSymbol',  'idx_symbol_emb',     'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('CodeFile',    'idx_codefile_emb',   'embedding',  metric := 'cosine');
CALL CREATE_VECTOR_INDEX('JinaIssue',   'idx_jina_issue_emb', 'embedding',  metric := 'cosine');


// =============================================================================
// FULL-TEXT SEARCH INDEXES  (Hybrid search — reduces Ollama tax for keyword queries)
// =============================================================================

CALL CREATE_FTS_INDEX('Memory',     'fts_memory_content',  ['content']);
CALL CREATE_FTS_INDEX('Note',       'fts_note_body',       ['body', 'title']);
CALL CREATE_FTS_INDEX('Task',       'fts_task_desc',       ['description', 'title']);
CALL CREATE_FTS_INDEX('Decision',   'fts_decision_rat',    ['rationale', 'title']);
CALL CREATE_FTS_INDEX('Violation',  'fts_violation_desc',  ['description']);
CALL CREATE_FTS_INDEX('CodeSymbol', 'fts_symbol_name',     ['name', 'signature']);
CALL CREATE_FTS_INDEX('CodeFile',   'fts_codefile_path',   ['path', 'name', 'summary']);
CALL CREATE_FTS_INDEX('JinaIssue',  'fts_jina_issue_text', ['issue_key', 'title', 'description']);


// =============================================================================
// EXAMPLE QUERIES
// =============================================================================

// ---------------------------------------------------------------------------
// 1. Semantic search across ALL memory kinds for a given query vector
//    (replace $qvec with an actual FLOAT[1536] at call time)
// ---------------------------------------------------------------------------
//
// CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, 10)
// WITH node AS m, distance
// OPTIONAL MATCH (m)<-[:PROJECT_MEMORY]-(p:Project)
// OPTIONAL MATCH (m)<-[:BACKEND_MEMORY]-(b:Backend)
// RETURN m.kind, m.scope, m.content, p.name AS project, b.name AS backend, distance
// ORDER BY distance
// LIMIT 10;

// ---------------------------------------------------------------------------
// 2. Find tasks semantically similar to a query, scoped to a specific project
// ---------------------------------------------------------------------------
//
// CALL PROJECT_GRAPH_CYPHER(
//     'proj_tasks',
//     'MATCH (p:Project {id: $project_id})-[:HAS_TASK]->(t:Task) RETURN t'
// );
//
// CALL QUERY_VECTOR_INDEX('proj_tasks', 'idx_task_emb', $qvec, 5)
// RETURN node.title, node.status, node.priority, distance
// ORDER BY distance;

// ---------------------------------------------------------------------------
// 3. Full conversation replay for a session
// ---------------------------------------------------------------------------
//
// MATCH (c:Conversation {id: $conv_id})-[:CONVERSATION_MESSAGE]->(m:Message)
// RETURN m.role, m.content, m.created_at
// ORDER BY m.created_at;

// ---------------------------------------------------------------------------
// 4. Violation blast radius — which tasks and symbols are affected?
// ---------------------------------------------------------------------------
//
// MATCH (v:Violation {audit_id: $audit_id})
// OPTIONAL MATCH (v)<-[:TASK_VIOLATION]-(t:Task)
// OPTIONAL MATCH (v)<-[:SYMBOL_VIOLATION]-(s:CodeSymbol)
// RETURN v.rule, v.severity, v.status,
//        collect(t.title)  AS affected_tasks,
//        collect(s.name)   AS affected_symbols;

// ---------------------------------------------------------------------------
// 5. Decision lineage — follow supersession chain
// ---------------------------------------------------------------------------
//
// MATCH path = (d:Decision {id: $decision_id})-[:SUPERSEDES*]->(old:Decision)
// RETURN [n IN nodes(path) | n.title] AS lineage;

// ---------------------------------------------------------------------------
// 6. Cross-session memory recall: most relevant memories for a new message
// ---------------------------------------------------------------------------
//
// CALL QUERY_VECTOR_INDEX('Memory', 'idx_memory_emb', $qvec, 20)
// WITH node AS m, distance
// WHERE m.expires_at IS NULL OR m.expires_at > current_timestamp()
// RETURN m.kind, m.scope, m.content, m.confidence, distance
// ORDER BY distance
// LIMIT 10;
