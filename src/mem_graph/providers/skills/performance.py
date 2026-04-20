"""Performance optimization skill."""

from __future__ import annotations

from .base import SkillBundle

performance = SkillBundle(
    name="performance",
    description="Performance optimization patterns.",
    prompt_fragment=(
        "## Performance Standards\n"
        "Check for common performance issues:\n"
        "- Unbounded loops reading external input without constraints.\n"
        "- Repeated allocations that could be pre-allocated.\n"
        "- Overly large copies of structs/objects passed by value when reference is better.\n"
        "- Accidental O(N^2) algorithms in performance-critical paths."
    ),
    audit_rules=[],
    languages=["any"],
    intents=["audit", "optimize"],
    confidence="medium",
)
