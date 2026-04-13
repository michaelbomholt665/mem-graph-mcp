"""External integration MCP tools."""

from . import jira

mcp = jira.mcp

__all__ = ["jira", "mcp"]