"""Skill bundle base dataclass."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from ...models.audit import AuditRule

@dataclass
class SkillBundle:
    """A bundle of domain expertise that activates for specific tasks."""
    name: str
    description: str
    prompt_fragment: str
    audit_rules: list[AuditRule] = field(default_factory=list)
    tool_allowlist: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)  # ["python"], ["go"], ["any"]
    intents: list[str] = field(default_factory=list)  # ["audit"], ["fix"], ["any"]
    confidence: Literal["high", "medium", "low"] = "medium"
    metadata: dict = field(default_factory=dict)

    def to_prompt_fragment(self) -> str:
        """Get the prompt fragment for injection."""
        return self.prompt_fragment

    def matches(self, language: str, intent: str) -> float:
        """Return match score (0.0 to 1.0) for this language/intent."""
        lang_match = 1.0 if "any" in self.languages or language in self.languages else 0.5
        intent_match = 1.0 if "any" in self.intents or intent in self.intents else 0.5
        confidence_mult = {"high": 1.0, "medium": 0.8, "low": 0.6}[self.confidence]
        return (lang_match + intent_match) / 2.0 * confidence_mult
