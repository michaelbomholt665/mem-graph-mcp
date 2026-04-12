# Testing Documentation

## Purpose
This document explains the testing strategy for the Syntx Memory MCP Server, covering unit, integration, and end-to-end tests. It describes how to run tests and how they exercise server, tools, and agent interactions.

## Overview
The testing suite uses pytest with asyncio support for async operations. Tests focus on round-trip functionality against a real Ladybug database with mocked embeddings. The suite covers tool implementations, agent behavior, and integration scenarios.

## Testing Strategy
### Test Levels
**Unit Tests:**
- Individual tool function testing
- Database operation validation
- Embedding and utility function testing

**Integration Tests:**
- Multi-tool interaction scenarios
- Database transaction testing
- Cross-component workflows

**End-to-End Tests:**
- Full MCP protocol testing
- Agent execution workflows
- Real embedding and summarization

### Test Coverage Goals
- 80%+ code coverage
- All tool functions tested
- Critical error paths covered
- Database operations validated

## Test Structure
### Test Files
**tests/test_tools.py:**
- Round-trip tests for all tool modules
- Database integration tests
- Cross-module interaction tests

**tests/test_audit.py:**
- Audit agent testing
- Pydantic AI integration tests
- Agent workflow validation

### Test Fixtures
**Database Fixture:**
```python
@pytest.fixture()
async def conn(tmp_path):
    # Fresh DB for each test
    # Patches embeddings to return zero vectors
    # Initializes schema and indexes
```

**Embedding Mock:**
- All embed() calls return `FAKE_VEC = [0.0] * 768`
- Allows testing without Ollama
- Consistent vector values for testing

## Running Tests
### Prerequisites
1. Install test dependencies:
   ```bash
   pip install -e .[test]
   ```

2. Ensure Python 3.14+ is available

### Basic Test Execution
Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=src/syntx_mcp --cov-report=html
```

Run specific test file:
```bash
pytest tests/test_tools.py
```

Run specific test:
```bash
pytest tests/test_tools.py::test_memory_store_and_list
```

### Test Configuration
Environment variables for testing:
```bash
export LADYBUG_DB_PATH=/tmp/test.db
export OLLAMA_EMBED_DIM=768
```

### Parallel Execution
Run tests in parallel:
```bash
pytest -n auto
```

## Tool Testing
### Memory Tools Testing
**Test Coverage:**
- `memory_store`: Content storage, embedding generation, scoping
- `memory_recall`: Semantic search, filtering, ranking
- `memory_search`: Cross-scope search
- `memory_expire`: Soft deletion, filtering
- `memory_list`: Unranked browsing

**Example Test:**
```python
async def test_memory_store_and_list(conn):
    result = await memory_store(content="test", kind="fact")
    assert result["memory_id"]
    listing = await memory_list()
    assert len(listing["memories"]) == 1
```

### Conversation Tools Testing
**Test Coverage:**
- `conversation_start`: Node creation, agent linking
- `conversation_append`: Message chaining, embedding
- `conversation_end`: Summary generation, finalization
- `conversation_get`: Full conversation retrieval

**Integration Test:**
```python
async def test_conversation_start_append_get(conn):
    started = await conversation_start(project_id=pid, agent_name="a", model="m")
    m1 = await conversation_append(id=started["conversation_id"], role="user", content="hi")
    got = await conversation_get(id=started["conversation_id"])
    assert len(got["messages"]) == 1
```

### Task Tools Testing
**Test Coverage:**
- `task_create`: Task creation, project linking
- `task_update`: Status/priority changes, completion tracking
- `task_get`: Full task retrieval with relationships
- `task_search`: Semantic search
- `task_link_decision`: Relationship creation
- `task_block`: Dependency management

**Relationship Test:**
```python
async def test_task_link_decision(conn):
    task = await task_create(project_id=pid, title="t", description="d")
    decision = await decision_record(project_id=pid, title="d", rationale="r")
    await task_link_decision(task["task_id"], decision["decision_id"])
    got = await task_get(task["task_id"])
    assert len(got["task"]["decisions"]) == 1
```

### Decision Tools Testing
**Test Coverage:**
- `decision_record`: Decision creation, embedding
- `decision_supersede`: Relationship management
- `decision_get`: Lineage retrieval
- `decision_search`: Semantic search

**Supersession Test:**
```python
async def test_decision_record_and_supersede(conn):
    old = await decision_record(project_id=pid, title="old", rationale="r")
    new = await decision_record(project_id=pid, title="new", rationale="r2")
    await decision_supersede(old["decision_id"], new["decision_id"], reason="better")
    got_old = await decision_get(old["decision_id"])
    assert got_old["decision"]["status"] == "superseded"
```

### Notes Tools Testing
**Test Coverage:**
- `note_create`: Note creation with tags
- `note_search`: Semantic search
- `note_list`: Filtering by project/kind

**Tagging Test:**
```python
async def test_note_create_and_list(conn):
    note = await note_create(project_id=pid, kind="warning", title="t", body="b", tags=["test"])
    listing = await note_list(project_id=pid, kind="warning")
    assert len(listing["notes"]) == 1
    assert listing["notes"][0]["tags"] == ["test"]
```

### Violation Tools Testing
**Test Coverage:**
- `violation_record`: Violation creation
- `violation_resolve`: Status updates
- `violation_recur`: Recurrence handling
- `violation_search`: Semantic search
- `violation_list`: Status filtering

**Lifecycle Test:**
```python
async def test_violation_record_and_resolve(conn):
    v = await violation_record(project_id=pid, audit_id="001A", rule="CWE-252", ...)
    await violation_resolve(v["violation_id"])
    listing = await violation_list(project_id=pid, status="resolved")
    assert len(listing["violations"]) == 1
```

### Project Tools Testing
**Test Coverage:**
- `project_create`: Project creation, embedding
- `project_get`: Project retrieval
- `project_list`: All projects listing
- `project_search`: Semantic search

**Basic CRUD:**
```python
async def test_project_create_and_get(conn):
    result = await project_create(name="Test", description="desc")
    got = await project_get(result["project_id"])
    assert got["project"]["name"] == "Test"
```

## Agent Testing
### Audit Agent Testing
**Test Coverage:**
- Agent initialization with dependencies
- Tool call mocking
- Result validation
- Dependency injection

**Example Test:**
```python
async def test_audit_agent_tool_calls():
    model = TestModel(custom_result_text='{"summary": "test", "new_smells_discovered": ["smell"]}')
    deps = AuditDependencies(...)
    with audit_agent.override(model=model):
        result = await audit_agent.run("audit", deps=deps)
        assert result.data.new_smells_discovered == ["smell"]
```

### Agent Integration Testing
**Test Scenarios:**
- Full audit workflow
- File reading and analysis
- Registry and guide updates
- Error handling

## Test Utilities
### Mocking
**Embedding Mock:**
- Consistent zero vectors for testing
- No external Ollama dependency
- Deterministic search results

**Database Mock:**
- In-memory database option
- Isolated test databases
- Fast test execution

### Test Data
**Factories:**
- Project/test data creation helpers
- Consistent test data generation
- Reusable test fixtures

### Assertions
**Custom Assertions:**
- Graph structure validation
- Relationship verification
- Embedding vector checks

## Continuous Integration
### CI Pipeline
```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.14'
      - run: pip install -e .[test]
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v3
```

### Coverage Requirements
- Minimum 80% coverage
- No coverage decrease allowed
- Coverage report generation

## Performance Testing
### Load Testing
**Tool Call Load:**
- Concurrent tool invocations
- Memory usage monitoring
- Response time measurement

**Database Load:**
- High-volume data insertion
- Complex query performance
- Index effectiveness validation

### Benchmarking
**Embedding Performance:**
- Vector generation timing
- Search query performance
- Index query optimization

## Test Maintenance
### Test Flakiness
**Sources of Flakiness:**
- Database state leakage
- Async timing issues
- External service dependencies

**Mitigation:**
- Isolated test databases
- Proper async/await usage
- Mock external services

### Test Data Management
**Data Cleanup:**
- Automatic database cleanup
- Fixture teardown
- Temporary file removal

**Data Consistency:**
- Deterministic test data
- Version-controlled test fixtures
- Reproducible test environments

## References to Code
- Test fixtures: `tests/conftest.py`
- Tool tests: `tests/test_tools.py`
- Agent tests: `tests/test_audit.py`
- Test configuration: `pytest.ini`
- Coverage configuration: `pyproject.toml`
