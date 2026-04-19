"""Registry for public sub-agent metadata exposed to MCP clients."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentEntry:
    """Public metadata for a registered sub-agent tool."""

    name: str
    tool_name: str
    description: str
    namespace: str
    categories: list[str] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "tool": self.tool_name,
            "description": self.description,
            "namespace": self.namespace,
            "categories": list(self.categories),
            "task_types": list(self.task_types),
        }


_AGENTS: dict[str, AgentEntry] = {}


def register_agent(entry: AgentEntry) -> None:
    """Register or replace a public sub-agent entry."""
    _AGENTS[entry.tool_name] = entry


def all_agents() -> list[AgentEntry]:
    """Return all registered public sub-agents sorted by name."""
    return sorted(_AGENTS.values(), key=lambda entry: entry.name)
