"""Documentation skill."""

from __future__ import annotations

from .base import SkillBundle

documentation = SkillBundle(
    name="documentation",
    description="Documentation best practices.",
    prompt_fragment=(
        "## Documentation Standards\n"
        "Assess code documentation:\n"
        "- Do public and exported functions/classes have clear docstrings?\n"
        "- Are complex logic paths explained via inline comments?\n"
        "- Is the module-level intent documented clearly?"
    ),
    audit_rules=[],
    languages=["any"],
    intents=["audit", "documentation"],
    confidence="medium",
)
