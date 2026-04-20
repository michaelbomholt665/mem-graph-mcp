# Design: Logfire Integration (Flight Recorder)

**Status:** Design Phase  
**Priority:** HIGH (Live visibility)  
**Date:** 2026-04-13

---

## Overview

Logfire is a structured logging and monitoring service from Pydantic. It acts as a "flight recorder"—capturing exactly what happens inside agents, graphs, and tools in **real-time**.

Unlike OpenTelemetry (which exports after the fact), Logfire provides:
1. **Live Streaming:** Watch agent decisions as they happen
2. **Searchable Logs:** Query past runs by agent, time, input
3. **Issue Tracking:** Automatic anomaly detection
4. **Timeline Visualization:** See the sequence of operations

---

## Goals

1. **Live Observability:** Watch agents thinking in real-time (debugging)
2. **Problem Diagnosis:** Quickly find root cause of failures
3. **Performance Profiling:** Identify bottlenecks during execution
4. **Historical Search:** Query logs from past runs
5. **Alert on Anomalies:** Flag unusual agent behavior

---

## Scope

### In Scope
- Initialize Logfire at server startup
- Instrument all agents with Logfire logging
- Capture planning phases (plans, revisions, verifications)
- Capture memory recalls and stores
- Capture graph queries and results
- Setup Logfire dashboard for monitoring
- Create alerts for anomalies

### Out of Scope
- Custom Logfire projects per user (single project)
- Real-time log streaming to clients (Logfire dashboard is canonical)
- Retaining logs beyond Logfire's retention policy

---

## Architecture

### 1. Logfire Setup

```python
# src/mem_graph/observability/logfire_setup.py

import logfire
from typing import Optional

def setup_logfire() -> None:
    """Initialize Logfire for the service."""
    
    logfire.configure(
        token=os.getenv("LOGFIRE_TOKEN", ""),
        project_name=os.getenv("LOGFIRE_PROJECT", "mem-graph"),
        environment=os.getenv("ENV", "dev"),
        # Capture both structured logs AND unstructured (print statements)
        console_colors=True if os.getenv("ENV") == "dev" else False,
    )
    
    logger.info("Logfire initialized", extra={
        "version": __version__,
        "env": os.getenv("ENV"),
        "logfire_project": os.getenv("LOGFIRE_PROJECT"),
    })

# Get Logfire instance
logfire_instance = logfire
```

### 2. Agent Instrumentation

Log detailed agent execution workflow:

```python
# src/mem_graph/agents/base_agent.py

import logfire

class LogfireAgent:
    """Base agent with Logfire instrumentation."""
    
    def __init__(self, agent: Agent, agent_name: str, project_id: str = ""):
        self.agent = agent
        self.agent_name = agent_name
        self.project_id = project_id
        self.logger = logfire.get_logger(agent_name)
    
    async def run(self, prompt: str, context: dict) -> str:
        """Run agent with full Logfire logging."""
        
        with self.logger.scope(f"{self.agent_name}.run") as span:
            span.set_attribute("project_id", self.project_id)
            span.set_attribute("prompt_length", len(prompt))
            
            # Log input
            self.logger.info(
                "Agent input",
                input_length=len(prompt),
                input_preview=prompt[:100],
            )
            
            try:
                # Call agent
                start = time.time()
                result = await self.agent.run(prompt)
                duration = time.time() - start
                
                # Log output
                self.logger.info(
                    "Agent output",
                    output_length=len(result.data),
                    output_preview=result.data[:100],
                    duration_seconds=duration,
                )
                
                span.set_attribute("success", True)
                span.set_attribute("output_length", len(result.data))
                span.set_attribute("duration_seconds", duration)
                
                return result
            
            except Exception as e:
                self.logger.error(
                    "Agent execution failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
                raise

# Usage
audit_agent = LogfireAgent(
    create_audit_agent(),
    agent_name="audit",
    project_id="proj-123"
)
```

### 3. Planning Phase Logging

Log planning workflow (crucial for debugging):

```python
# src/mem_graph/agents/planning_agent.py

class LogfirePlanningAgent(PlanningAgent):
    """Planning agent with Logfire instrumentation."""
    
    def __init__(self, agent: Agent, graph: GraphClient, project_id: str):
        super().__init__(agent, graph, project_id)
        self.logger = logfire.get_logger(f"planning.{agent_name}")
    
    async def create_plan(self, task: str, context: str) -> Plan:
        """Create plan with logging."""
        
        with self.logger.scope("create_plan") as span:
            self.logger.info(
                "Creating plan",
                task=task,
                context_length=len(context),
            )
            
            # Call agent to create plan
            plan = await super().create_plan(task, context)
            
            # Log plan
            self.logger.info(
                "Plan created",
                plan_id=plan.plan_id,
                step_count=len(plan.steps),
                steps=[
                    {
                        "id": s.id,
                        "description": s.description,
                        "expected_output": s.expected_output,
                    }
                    for s in plan.steps
                ],
                rationale=plan.rationale,
            )
            
            span.set_attribute("plan_id", plan.plan_id)
            span.set_attribute("step_count", len(plan.steps))
            
            return plan
    
    async def execute_with_plan(self, task: str, context: str) -> tuple[str, Plan]:
        """Execute with plan logging."""
        
        with self.logger.scope("execute_with_plan") as span:
            # Get plan (logged above)
            plan = await self.create_plan(task, context)
            
            # Execute
            with self.logger.scope("execute"):
                self.logger.info("Executing per plan", plan_id=plan.plan_id)
                output = await self.agent.run(...)
                
                self.logger.info(
                    "Execution complete",
                    output_length=len(output),
                    plan_id=plan.plan_id,
                )
            
            # Verify
            with self.logger.scope("verify"):
                self.logger.info("Verifying output against plan", plan_id=plan.plan_id)
                verification = await self.verify_against_plan(task, plan, output)
                
                self.logger.info(
                    "Verification result",
                    passed=verification["passed"],
                    failures=verification.get("failures", []),
                    plan_id=plan.plan_id,
                )
            
            # Self-correct if needed
            if not verification["passed"]:
                with self.logger.scope("self_correct"):
                    self.logger.info(
                        "Self-correcting",
                        failure_count=len(verification["failures"]),
                        plan_id=plan.plan_id,
                    )
                    corrected = await self.self_correct(
                        plan,
                        output,
                        verification["failures"],
                    )
                    output = corrected
                    
                    self.logger.info(
                        "Self-correction complete",
                        plan_id=plan.plan_id,
                    )
            
            span.set_attribute("plan_id", plan.plan_id)
            span.set_attribute("verification_passed", verification["passed"])
            
            return output, plan
```

### 4. Memory Operations Logging

Log what agents remember and forget:

```python
# src/mem_graph/services/memory.py

class LogfireMemory:
    """Memory operations with Logfire instrumentation."""
    
    def __init__(self):
        self.logger = logfire.get_logger("memory")
    
    async def store_fact(self, content: str, tags: list[str]) -> str:
        """Store fact with logging."""
        
        with self.logger.scope("store_fact"):
            self.logger.info(
                "Storing fact",
                content_length=len(content),
                tags=tags,
            )
            
            fact_id = await self._do_store(content, tags)
            
            self.logger.info(
                "Fact stored",
                fact_id=fact_id,
                content_preview=content[:50],
            )
            
            return fact_id
    
    async def recall_facts(self, query: str, limit: int = 5) -> list[dict]:
        """Recall facts with logging."""
        
        with self.logger.scope("recall_facts"):
            self.logger.info(
                "Recalling facts",
                query=query,
                limit=limit,
            )
            
            start = time.time()
            facts = await self._do_recall(query, limit)
            duration = time.time() - start
            
            self.logger.info(
                "Facts recalled",
                fact_count=len(facts),
                query=query,
                duration_seconds=duration,
                confidence=[
                    {"fact_id": f["id"], "confidence": f["confidence"]}
                    for f in facts
                ],
            )
            
            return facts
```

### 5. Graph Query Logging

Log database interactions:

```python
# src/mem_graph/db.py

class LogfireGraphClient:
    """Graph client with Logfire instrumentation."""
    
    def __init__(self, connection):
        self.connection = connection
        self.logger = logfire.get_logger("graph")
    
    async def query(self, cypher: str, **params) -> list[dict]:
        """Execute Cypher query with logging."""
        
        with self.logger.scope("cypher_query") as span:
            self.logger.info(
                "Graph query",
                query_length=len(cypher),
                query_preview=cypher[:100],
                param_keys=list(params.keys()),
            )
            
            try:
                start = time.time()
                result = await self.connection.query(cypher, **params)
                duration = time.time() - start
                
                self.logger.info(
                    "Graph query result",
                    result_count=len(result),
                    duration_seconds=duration,
                    query_preview=cypher[:100],
                )
                
                span.set_attribute("result_count", len(result))
                span.set_attribute("duration_seconds", duration)
                
                return result
            
            except Exception as e:
                self.logger.error(
                    "Graph query failed",
                    error=str(e),
                    query_preview=cypher[:100],
                )
                raise
```

### 6. Tool Instrumentation

Log all FastMCP tool calls:

```python
# src/mem_graph/tools/decorators.py

def logfire_tool(tool_name: str):
    """Decorator to log all tool calls."""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            logger = logfire.get_logger(f"tool.{tool_name}")
            
            with logger.scope(tool_name) as span:
                logger.info(
                    "Tool called",
                    tool_name=tool_name,
                    args_keys=list(kwargs.keys()),
                )
                
                try:
                    start = time.time()
                    result = await func(*args, **kwargs)
                    duration = time.time() - start
                    
                    logger.info(
                        "Tool completed",
                        tool_name=tool_name,
                        duration_seconds=duration,
                        result_preview=str(result)[:100],
                    )
                    
                    span.set_attribute("success", True)
                    span.set_attribute("duration_seconds", duration)
                    
                    return result
                
                except Exception as e:
                    logger.error(
                        "Tool failed",
                        tool_name=tool_name,
                        error=str(e),
                    )
                    span.set_attribute("success", False)
                    span.set_attribute("error", str(e))
                    raise
        
        return wrapper
    return decorator

# Apply to tools
@mcp.tool()
@logfire_tool("memory_store")
async def memory_store(content: str, tags: list[str] | None = None) -> dict:
    """Store fact (automatically logged)."""
    pass
```

### 7. Logfire Dashboard Alerts

Setup alerts for anomalies:

```python
# Configure alerts in Logfire UI or via API

{
  "alerts": [
    {
      "name": "Agent execution timeout",
      "condition": "agent.run.duration_seconds > 60",
      "action": "email"
    },
    {
      "name": "High error rate",
      "condition": "tool.success_rate < 0.90",
      "action": "slack"
    },
    {
      "name": "Memory recall empty",
      "condition": "memory.recall_facts.result_count == 0",
      "action": "log"
    },
  ]
}
```

---

## Logfire Dashboard Usage

Once instrumented, you get:

1. **Live Feed:** See logs as they stream in real-time
2. **Search:** `agent:audit error:true` to find failed audit runs
3. **Timeline:** Watch sequence of operations (plan → execute → verify)
4. **Metrics:** Duration histograms, error rates by tool
5. **Alerts:** Get notified of anomalies

### Example Queries

```
# Find all audit agent failures
log.level = ERROR AND agent = audit

# Find slow executions
agent_duration_seconds > 30

# Find memory recalls with no results
tool = "memory_recall" AND result_count = 0

# Find today's planning failures
timestamp >= today AND scope = "planning.create_plan" AND success = false
```

---

## Benefits

1. **Real-Time Debugging:** Watch what agents are thinking
2. **Quick Diagnosis:** Search logs to find root cause
3. **Performance Profiling:** Identify slow operations
4. **Anomaly Detection:** Built-in alerts
5. **Historical Analysis:** Query logs from weeks ago

---

## Configuration

```bash
# .env

LOGFIRE_TOKEN=<your-logfire-token>
LOGFIRE_PROJECT=mem-graph
ENV=dev  # or staging, production
```

---

## Implementation Checklist

- [ ] Setup Logfire account and get token
- [ ] Initialize Logfire in server startup
- [ ] Add Logfire instrumentation to Core Five agents
- [ ] Add Logfire logging to PlanningAgent (plan → verify → correct)
- [ ] Add Logfire logging to memory operations
- [ ] Add Logfire logging to graph queries
- [ ] Add `@logfire_tool` decorator to all tools
- [ ] Setup Logfire dashboard in UI
- [ ] Create alert rules (timeout, error rate, anomalies)
- [ ] Document how to search Logfire logs
- [ ] Create on-call runbook using Logfire

---

## Success Criteria

1. All agent operations are logged to Logfire
2. Can replay past runs via Logfire timeline
3. Can search logs by agent, tool, status
4. Alerts fire when anomalies detected
5. Team can quickly diagnose issues via Logfire

---

## Dependencies

- `logfire>=4.32.0` (already in `pyproject.toml`)
- Logfire account (free tier available)
- API token for authentication

---

## Integration with OpenTelemetry

Logfire complements OpenTelemetry:
- **OTel:** Infrastructure traces (latency, metrics)
- **Logfire:** Business logic traces (agent decisions, memory operations)

Both can run together—Logfire provides user-facing visibility, OTel powers alerts.

---

## Notes

- Logfire is opinionated about Python logging (good—standardized)
- Free tier supports 100k log entries/month (plenty for dev)
- Paid tier removes limits
- Logs are retained for 30 days by default (can extend)
- PII can be masked via Logfire rules
