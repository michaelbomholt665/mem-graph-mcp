Good, got both the PydanticAI and MCP integration pages. Here's the plan:

---

# Plan: Instrument MCP Agents in Logfire

## Context

The Logfire Agents view detects agents via **OpenTelemetry semantic conventions** — specifically spans where `span_name = 'invoke_agent'` AND `gen_ai.operation.name = 'invoke_agent'`. These spans are emitted automatically when you use `logfire.instrument_pydantic_ai()` and/or `logfire.instrument_mcp()`. Your dashboard shows "0 active agents" because your MCP server processes aren't emitting those spans yet.

---

## Step 1 — Install dependencies

```bash
pip install logfire mcp 'pydantic-ai-slim[openai]'  # swap openai for your actual provider
```

---

## Step 2 — Instrument the MCP server

In every MCP server process (your `mem_graph` FastMCP server), add Logfire instrumentation near the top, **before** any routes or tools are registered:

```python
import logfire

logfire.configure(service_name='mem_graph')  # use a meaningful name per server
logfire.instrument_mcp()
```

The `service_name` is what will label the agent in the Logfire UI.

---

## Step 3 — Instrument the MCP client / agent runner

In any client-side code that invokes agents (the process calling your MCP server):

```python
import logfire
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

logfire.configure(service_name='syntx-agent')
logfire.instrument_pydantic_ai()  # produces the invoke_agent spans Logfire listens for
logfire.instrument_mcp()          # links client ↔ server in distributed traces

server = MCPServerStreamableHTTP('http://localhost:8000/mcp')
agent = Agent('your-model-here', toolsets=[server])
```

Both `instrument_pydantic_ai()` and `instrument_mcp()` should be called in the **same process** for full distributed trace correlation. `instrument_pydantic_ai()` is what actually emits the `invoke_agent` span that triggers Logfire's Agents view.

---

## Step 4 — Verify the write token

Logfire needs to know where to send traces. Set the token either via env var or in `configure()`:

```bash
export LOGFIRE_TOKEN=your_write_token_here
```

or

```python
logfire.configure(service_name='mem_graph', token='your_write_token_here')
```

Your write token is under **Settings → Write Tokens** in the Logfire UI (the `memgraph / all envs` project shown in the screenshot).

---

## Step 5 — Run both processes and trigger an agent call

Start server, then client, then invoke an agent run. Logfire's Agents view auto-populates once it receives a span where `gen_ai.operation.name = 'invoke_agent'`. No manual registration is needed — the instrumentation emits the right spans and Logfire picks them up.

---

## Step 6 — Confirm in the UI

Navigate to **AI Engineering → Agents**. After the first instrumented agent run completes you should see the agent listed with run count, latency, and token metrics. Use the `24h / 7d / 30d` selector to adjust the window if it doesn't appear immediately.

---

## Notes for your architecture

- Since `mem_graph` uses **streamable HTTP transport**, the `MCPServerStreamableHTTP` client class is the correct pairing on the agent side.
- If you run multiple MCP servers (e.g. separate servers per tool domain), call `logfire.configure(service_name='...')` + `logfire.instrument_mcp()` in **each** server process. Each will appear as a distinct service in Logfire traces.
- The `logfire.instrument_pydantic_ai()` call is what registers the `invoke_agent` span — without it, MCP tool traces will show up in the Live view but **not** in the Agents tab.

read pyproject.toml .env and src/mem_graph/observability/logfire.py for more information.
