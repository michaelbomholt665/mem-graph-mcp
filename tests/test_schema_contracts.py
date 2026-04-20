from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from mem_graph.models.schema_contracts import (
    find_schema_contract_violations,
    iter_schema_models,
)


def test_maintained_schema_modules_have_no_contract_violations() -> None:
    violations = find_schema_contract_violations(iter_schema_models())
    assert violations == []


def test_schema_contract_checker_reports_weak_types_and_missing_descriptions() -> None:
    class WeakSchema(BaseModel):
        payload: dict = Field(description="Bad bare mapping.")
        metadata: dict[str, Any] = Field(description="Bad Any mapping.")
        phase: str = Field(description="Bad plain enum-like string.")
        undocumented: int

    violations = find_schema_contract_violations([WeakSchema])

    assert any(
        "payload: uses untyped dict mapping" in violation for violation in violations
    )
    assert any("metadata: uses Any" in violation for violation in violations)
    assert any(
        "phase: should use Literal or Enum instead of plain str" in violation
        for violation in violations
    )
    assert any(
        "undocumented: missing Field description" in violation
        for violation in violations
    )
