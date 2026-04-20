"""Internal skill registry for category and task-type dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from .base import SkillBundle


@dataclass(frozen=True, slots=True)
class SkillEntry:
    """Metadata used to resolve an internal skill for a task."""

    name: str
    category: str
    task_types: list[str]
    description: str = ""
    static_priority: int = 0
    eval_score: float = 1.0

    @property
    def dispatch_score(self) -> float:
        """Return the combined manual and eval-based priority."""
        return self.static_priority * self.eval_score


_SKILLS: list[SkillEntry] = []


def register_skill(skill: SkillEntry) -> None:
    """Register an internal skill candidate, ignoring duplicates by name."""
    if any(s.name == skill.name for s in _SKILLS):
        return
    _SKILLS.append(skill)


def all_skills() -> list[SkillEntry]:
    """Return all registered internal skills."""
    return list(_SKILLS)


def resolve_skill(category: str, task_type: str) -> SkillEntry | None:
    """Resolve the best skill for a category and task type."""
    candidates = [
        skill
        for skill in _SKILLS
        if skill.category == category and task_type in skill.task_types
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda skill: skill.dispatch_score)


def task_type_map() -> dict[str, list[str]]:
    """Return the public category-to-task-type capability map."""
    task_types: dict[str, set[str]] = {}
    for skill in _SKILLS:
        task_types.setdefault(skill.category, set()).update(skill.task_types)
    return {
        category: sorted(types)
        for category, types in sorted(task_types.items(), key=lambda item: item[0])
    }

class SkillRegistry:
    def __init__(self) -> None:
        self.skills: dict[str, SkillBundle] = {}

    def register(self, skill: SkillBundle) -> None:
        self.skills[skill.name] = skill

    def get(self, name: str) -> SkillBundle:
        if name not in self.skills:
            raise ValueError(f"Skill {name} not found")
        return self.skills[name]

    def list_all(self) -> list[str]:
        return list(self.skills.keys())

    def filter(self, language: str, intent: str) -> list[tuple[SkillBundle, float]]:
        """Return skills matching language/intent, sorted by match score."""
        matches = []
        for skill in self.skills.values():
            score = skill.matches(language, intent)
            if score > 0.0:
                matches.append((skill, score))
        return sorted(matches, key=lambda x: x[1], reverse=True)

SKILL_REGISTRY = SkillRegistry()

def load_skill(name: str) -> SkillBundle:
    """Load a specific skill by name."""
    return SKILL_REGISTRY.get(name)

def skills_match(language: str, intent: str) -> SkillBundle | None:
    """Return the best-matching skill for language/intent."""
    matches = SKILL_REGISTRY.filter(language, intent)
    return matches[0][0] if matches else None
