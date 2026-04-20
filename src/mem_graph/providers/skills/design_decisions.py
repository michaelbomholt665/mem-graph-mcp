"""Design decisions and ADR skill."""

from __future__ import annotations

from .base import SkillBundle

design_decisions = SkillBundle(
    name="design_decisions",
    description="Architecture Decision Records (ADR) and design documentation guidelines.",
    prompt_fragment=(
        "## Architecture Decision Records (ADRs)\n"
        "When documenting important architectural or design choices, produce an ADR:\n"
        "1. **Title:** A short, descriptive name (e.g., '001-use-postgres').\n"
        "2. **Status:** Proposed, Accepted, Rejected, Deprecated, or Superseded.\n"
        "3. **Context:** Provide the underlying problem, business drivers, and constraints.\n"
        "4. **Decision:** State clearly what is being chosen and how it works.\n"
        "5. **Alternatives Considered:** List other options that were evaluated and why they were dismissed.\n"
        "6. **Consequences:** Explain the positive and negative trade-offs of this decision.\n"
        "\n"
        "Keep the document concise, immutable once accepted, and focus heavily on *why* the decision was made."
    ),
    audit_rules=[],
    languages=["any"],
    intents=["design", "planning", "documentation"],
    confidence="high",
)
