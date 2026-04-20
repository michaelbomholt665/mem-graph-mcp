"""Validation helpers for maintained schema contracts.

These checks intentionally target the model modules that act as public schema
surfaces for agent I/O and graph-facing structured data. The goal is to fail
fast when new fields fall back to weak types such as ``Any`` or undocumented
bare mappings.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from types import ModuleType
from typing import Annotated, Any, get_args, get_origin

from pydantic import BaseModel

SCHEMA_MODULES = (
    "mem_graph.models.agent_outputs",
    "mem_graph.models.audit",
    "mem_graph.models.evals",
    "mem_graph.models.work",
    "mem_graph.models.task",
)

_ENUM_LIKE_FIELD_NAMES = {"phase", "intent", "relationship_kind", "ask_user_policy"}


def iter_schema_models(
    module_names: Iterable[str] = SCHEMA_MODULES,
) -> list[type[BaseModel]]:
    """Return BaseModel subclasses defined in the maintained schema modules."""

    models: list[type[BaseModel]] = []
    for module_name in module_names:
        module = import_module(module_name)
        models.extend(_module_models(module))
    return sorted(models, key=lambda model: (model.__module__, model.__name__))


def find_schema_contract_violations(
    models: Iterable[type[BaseModel]],
) -> list[str]:
    """Return human-readable contract violations for the provided schema models."""

    violations: list[str] = []
    for model in models:
        for field_name, field_info in model.model_fields.items():
            violations.extend(_field_contract_violations(model, field_name, field_info))

    return violations


def _field_contract_violations(
    model: type[BaseModel],
    field_name: str,
    field_info: object,
) -> list[str]:
    annotation = getattr(field_info, "annotation")
    qualified_name = f"{model.__module__}.{model.__name__}.{field_name}"
    violations: list[str] = []

    if not (getattr(field_info, "description", "") or "").strip():
        violations.append(f"{qualified_name}: missing Field description")

    if _annotation_uses_any(annotation):
        violations.append(f"{qualified_name}: uses Any")

    if _contains_untyped_mapping(annotation):
        violations.append(f"{qualified_name}: uses untyped dict mapping")

    if field_name in _ENUM_LIKE_FIELD_NAMES and _is_plain_string(annotation):
        violations.append(
            f"{qualified_name}: should use Literal or Enum instead of plain str"
        )

    return violations


def _module_models(module: ModuleType) -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    for value in module.__dict__.values():
        if (
            isinstance(value, type)
            and issubclass(value, BaseModel)
            and value is not BaseModel
            and value.__module__ == module.__name__
        ):
            models.append(value)
    return models


def _annotation_uses_any(annotation: object, seen: set[int] | None = None) -> bool:
    if annotation is Any:
        return True

    seen = seen or set()
    marker = id(annotation)
    if marker in seen:
        return False
    seen.add(marker)

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None:
        if origin is Annotated and args:
            return _annotation_uses_any(args[0], seen)
        return any(_annotation_uses_any(arg, seen) for arg in args)
    return False


def _contains_untyped_mapping(annotation: object, seen: set[int] | None = None) -> bool:
    seen = seen or set()
    marker = id(annotation)
    if marker in seen:
        return False
    seen.add(marker)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated and args:
        return _contains_untyped_mapping(args[0], seen)

    if annotation is dict or origin is dict:
        if len(args) != 2:
            return True
        key_type, value_type = args
        return (
            value_type in {Any, object}
            or _contains_untyped_mapping(key_type, seen)
            or _contains_untyped_mapping(value_type, seen)
        )

    if origin is None:
        return False
    return any(_contains_untyped_mapping(arg, seen) for arg in args)


def _is_plain_string(annotation: object) -> bool:
    if annotation is str:
        return True

    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated and args:
        return _is_plain_string(args[0])
    if origin is None:
        return False

    filtered = [arg for arg in args if arg is not type(None)]
    return len(filtered) == 1 and filtered[0] is str


__all__ = [
    "SCHEMA_MODULES",
    "find_schema_contract_violations",
    "iter_schema_models",
]
