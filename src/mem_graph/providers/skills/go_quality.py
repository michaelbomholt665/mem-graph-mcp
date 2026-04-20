"""Go quality skill."""

from __future__ import annotations

from ...agents.audit.rules.go import GO_RULES
from .base import SkillBundle

go_quality = SkillBundle(
    name="go_quality",
    description="Go-specific code quality rules.",
    prompt_fragment=(
        "## Go Quality Standards\n"
        "Apply these Go-specific rules:\n"
        "- Handle all errors explicitly.\n"
        "- Ensure contexts are properly propagated.\n"
        "- Avoid goroutine leaks by ensuring exit conditions.\n"
        "- Be careful with deferred calls inside loops."
    ),
    audit_rules=GO_RULES,
    languages=["go"],
    intents=["audit", "fix"],
    confidence="high",
)
