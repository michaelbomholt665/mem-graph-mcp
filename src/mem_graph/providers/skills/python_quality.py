"""Python quality skill."""

from __future__ import annotations

from ...agents.audit.rules.python import PYTHON_RULES
from .base import SkillBundle

python_quality = SkillBundle(
    name="python_quality",
    description="Python-specific code quality rules.",
    prompt_fragment=(
        "## Python Quality Standards\n"
        "Apply these Python-specific rules:\n"
        "- Follow PEP 8 guidelines for formatting and naming.\n"
        "- Be mindful of mutable default arguments.\n"
        "- Avoid bare except statements."
    ),
    audit_rules=PYTHON_RULES,
    languages=["python"],
    intents=["audit", "fix"],
    confidence="high",
)
