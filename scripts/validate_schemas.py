#!/usr/bin/env python3
"""Validate maintained schema modules against the repository contract checks."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mem_graph.models.schema_contracts import (  # noqa: E402
    find_schema_contract_violations,
    iter_schema_models,
)


def main() -> int:
    models = iter_schema_models()
    violations = find_schema_contract_violations(models)

    if violations:
        print("Schema contract validation FAILED:\n")
        for violation in violations:
            print(f"  - {violation}")
        print(f"\n{len(violations)} violation(s) found across {len(models)} model(s).")
        return 1

    print(
        "Schema contract validation PASSED - "
        f"{len(models)} model(s) checked with no contract violations."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
