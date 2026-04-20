"""Security skill."""

from __future__ import annotations

from ...agents.audit.rules.security import SECURITY_RULES
from .base import SkillBundle

security = SkillBundle(
    name="security",
    description="Cross-language security rules.",
    prompt_fragment=(
        "## Security Audit Focus\n"
        "- Detect hardcoded credentials (API keys, passwords, tokens)\n"
        "- Flag SQL injection vectors (unparameterised queries)\n"
        "- Identify XSS vulnerabilities (unescaped user input)\n"
        "- Check for insecure deserialization\n"
        "- Verify TLS/SSL usage"
    ),
    audit_rules=SECURITY_RULES,
    languages=["any"],
    intents=["audit", "security_hardening"],
    confidence="high",
)
