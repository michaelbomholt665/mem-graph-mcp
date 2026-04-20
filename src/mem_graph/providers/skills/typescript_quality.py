"""TypeScript quality skill."""

from __future__ import annotations

from .base import SkillBundle

typescript_quality = SkillBundle(
    name="typescript_quality",
    description="TypeScript-specific patterns and rules.",
    prompt_fragment=(
        "## TypeScript Quality Standards\n"
        "Apply these TypeScript-specific rules:\n"
        "- Use strict typing; avoid `any` where possible.\n"
        "- Prefer `interface` over `type` for object shapes unless union/intersection is needed.\n"
        "- Handle asynchronous operations safely with try/catch or .catch().\n"
        "- Ensure proper null and undefined checking."
    ),
    audit_rules=[],
    languages=["typescript", "ts"],
    intents=["audit", "fix"],
    confidence="medium",
)
