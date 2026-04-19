"""Internal skill registry for category and task-type dispatch."""

from __future__ import annotations

from dataclasses import dataclass


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
    """Register an internal skill candidate."""
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
