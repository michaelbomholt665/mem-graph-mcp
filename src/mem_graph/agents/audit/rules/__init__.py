"""Composable audit rule sets."""

from __future__ import annotations

from ....models.audit import AuditRule
from .base import BASE_RULES
from .correctness import CORRECTNESS_RULES
from .go import GO_RULES
from .maintainability import MAINTAINABILITY_RULES
from .python import PYTHON_RULES
from .security import SECURITY_RULES

BUG_RULES: list[AuditRule] = [
    *BASE_RULES,
    *CORRECTNESS_RULES,
    *PYTHON_RULES,
]
SMELL_RULES: list[AuditRule] = [*MAINTAINABILITY_RULES]
DEFAULT_RULES: list[AuditRule] = [
    *GO_RULES,
    *BASE_RULES,
    *SECURITY_RULES,
    *CORRECTNESS_RULES,
    *MAINTAINABILITY_RULES,
    *PYTHON_RULES,
]

RULE_SET_REGISTRY: dict[str, list[AuditRule]] = {
    "default": DEFAULT_RULES,
    "security": SECURITY_RULES,
    "bug": BUG_RULES,
    "smell": SMELL_RULES,
    "go": GO_RULES,
    "python": PYTHON_RULES,
}


def audit_rules_get(rule_set: str = "default") -> list[AuditRule]:
    """Return a copy of a named audit rule set."""
    if rule_set not in RULE_SET_REGISTRY:
        raise ValueError(
            f"Unknown audit rule set: {rule_set}. "
            f"Available: {', '.join(sorted(RULE_SET_REGISTRY))}"
        )
    return list(RULE_SET_REGISTRY[rule_set])


__all__ = [
    "BASE_RULES",
    "BUG_RULES",
    "CORRECTNESS_RULES",
    "DEFAULT_RULES",
    "GO_RULES",
    "MAINTAINABILITY_RULES",
    "PYTHON_RULES",
    "RULE_SET_REGISTRY",
    "SECURITY_RULES",
    "SMELL_RULES",
    "audit_rules_get",
]
