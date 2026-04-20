from typing import Dict, List, Optional
from .markers import TIER_1, TIER_2, TIER_3

class ToolRegistry:
    def __init__(self) -> None:
        self.tier_1_tools: List[str] = []
        self.tier_2_tools: Dict[str, List[str]] = {}  # namespace -> [tool names]
        self.tier_3_tools: List[str] = []

    def register_tool(self, name: str, tier: str, namespace: Optional[str] = None) -> None:
        if tier == TIER_1:
            self.tier_1_tools.append(name)
        elif tier == TIER_2:
            ns = namespace or "misc"
            self.tier_2_tools.setdefault(ns, []).append(name)
        elif tier == TIER_3:
            self.tier_3_tools.append(name)

    def validate(self) -> List[str]:
        """Check that Tier 1 has <= 8 tools."""
        errors: List[str] = []
        if len(self.tier_1_tools) > 8:
            errors.append(f"Tier 1 has {len(self.tier_1_tools)} tools; max is 8. Tools: {self.tier_1_tools}")
        return errors

    def get_tier_1(self) -> List[str]:
        return self.tier_1_tools

    def get_tier_2_namespace(self, namespace: str) -> List[str]:
        return self.tier_2_tools.get(namespace, [])

tier_registry = ToolRegistry()
