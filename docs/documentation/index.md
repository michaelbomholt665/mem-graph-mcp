# Syntx Memory MCP Server Documentation

## Purpose
This documentation suite explains the architecture, components, and operation of the Syntx Memory MCP Server - a specialized agent memory system built on the Model Context Protocol (MCP) that captures conversations, tasks, decisions, notes, and violations with semantic recall capabilities.

## Overview
The Syntx Memory MCP Server consists of three core components working together:

1. **Server** - The MCP server foundation that handles tool discovery, lazy namespace activation, and HTTP/SSE transport
2. **Tools** - Specialized functional modules for memory storage, task management, conversation capture, and more
3. **Agent** - Autonomous agents that interact with the server and tools to perform work

## Table of Contents
- [Server Component](./server.md) - Server lifecycle, request handling, and tool discovery
- [Tools Component](./tools.md) - Tool discovery, invocation, and namespace activation
- [Agent Component](./agent.md) - Agent lifecycle, decision logic, and server/tool interactions
- [Architecture Overview](./architecture.md) - Component interactions, data flows, and external dependencies
- [API Reference](./api.md) - Public/internal endpoints, message formats, and event types
- [Data Models](./data-models.md) - Core schemas, node/relationship definitions, and example payloads
- [Configuration](./configuration.md) - Environment variables, config files, and override mechanisms
- [Deployment](./deployment.md) - Local development, staging, and production deployment guides
- [Security](./security.md) - Authentication, authorization, secrets handling, and auditing
- [Testing](./testing.md) - Testing strategies, test execution, and coverage guidelines
- [Runbook](./runbook.md) - Operational procedures, incident response, and troubleshooting
- [Glossary](./glossary.md) - Defined terms and acronyms

## Quick Start
```bash
# Install dependencies
pip install -e .

# Start the server (default: http://127.0.0.1:9100)
python -m mem-graph.server

# In another terminal, interact with the server using MCP clients
# Example: Use tools_search to discover available capabilities
```
