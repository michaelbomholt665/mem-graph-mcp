"""Compatibility re-exports for the historical workflow selector module."""

from __future__ import annotations

from .selection.selector import (
    WorkflowSelection,
    select_all,
    select_profile,
    select_reasoning_policy,
    select_workflow,
)

__all__ = [
    "WorkflowSelection",
    "select_all",
    "select_profile",
    "select_reasoning_policy",
    "select_workflow",
]
