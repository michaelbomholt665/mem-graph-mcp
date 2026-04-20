from typing import Any, Callable

from .tier_registry import TIER_1, TIER_2, TIER_3, tier_registry

def tier_1_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark tool as Tier 1: always loaded, visible to users."""
    setattr(func, "_tool_tier", TIER_1)
    tier_registry.register_tool(func.__name__, TIER_1)
    return func

def tier_2_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark tool as Tier 2: searchable by namespace, user-visible."""
    setattr(func, "_tool_tier", TIER_2)
    # The namespace could be extracted, but typically we won't know it here accurately.
    # The registration could just use 'default' namespace or parse tags if accessible.
    tier_registry.register_tool(func.__name__, TIER_2)
    return func

def hidden_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Mark tool as Tier 3: agent-local or invisible, not exposed to MCP clients."""
    setattr(func, "_tool_tier", TIER_3)
    tier_registry.register_tool(func.__name__, TIER_3)
    return func

def get_tool_tier(func: Callable[..., Any]) -> str:
    """Get the tier of a tool function."""
    return getattr(func, "_tool_tier", TIER_2)  # default to Tier 2
