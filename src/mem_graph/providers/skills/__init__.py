"""Skill bundles and registry."""

from __future__ import annotations

from .base import SkillBundle
from .registry import SkillRegistry, load_skill, skills_match, SKILL_REGISTRY
from .python_quality import python_quality
from .security import security
from .go_quality import go_quality
from .typescript_quality import typescript_quality
from .documentation import documentation
from .performance import performance
from .design_decisions import design_decisions

SKILL_REGISTRY.register(python_quality)
SKILL_REGISTRY.register(security)
SKILL_REGISTRY.register(go_quality)
SKILL_REGISTRY.register(typescript_quality)
SKILL_REGISTRY.register(documentation)
SKILL_REGISTRY.register(performance)
SKILL_REGISTRY.register(design_decisions)

__all__ = [
    "SkillBundle",
    "SkillRegistry",
    "load_skill",
    "skills_match",
    "SKILL_REGISTRY",
    "python_quality",
    "security",
    "go_quality",
    "typescript_quality",
    "documentation",
    "performance",
    "design_decisions",
]
