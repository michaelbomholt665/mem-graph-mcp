#!/usr/bin/env python3
# scripts/validate_prompt_caching.py
"""
Validate that the prompt system follows the three-layer caching architecture.

Checks:
1. All personas render without OCEAN float numbers.
2. PROMPT_REGISTRY contains all 4 reasoning-mode keys.
3. PROMPT_REGISTRY contains all 29 workflow-stage keys.
4. All stage prompts are non-empty strings.

Run:
    python scripts/validate_prompt_caching.py
"""

from __future__ import annotations

import re
import sys

# Add src to path for direct script execution
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from mem_graph.resources.personas import PERSONA_REGISTRY
from mem_graph.resources.prompts import PROMPT_REGISTRY

################
#   EXPECTED KEYS
################

EXPECTED_REASONING_KEYS = {
    "reasoning.react_challenge",
    "reasoning.react_2",
    "reasoning.bounded_tot",
    "reasoning.cot",
}

EXPECTED_STAGE_KEYS = {
    # feature_implementation
    "stage.feature_implementation.sentry",
    "stage.feature_implementation.logic_draft",
    "stage.feature_implementation.scribe",
    "stage.feature_implementation.validation",
    # refactor
    "stage.refactor.mapping",
    "stage.refactor.audit",
    "stage.refactor.scribe",
    "stage.refactor.validation",
    # security_hardening
    "stage.security_hardening.audit",
    "stage.security_hardening.fix",
    "stage.security_hardening.validation",
    # dependency_audit
    "stage.dependency_audit.discovery",
    "stage.dependency_audit.triage",
    "stage.dependency_audit.validation",
    # code_review
    "stage.code_review.sentry",
    "stage.code_review.audit",
    "stage.code_review.scribe",
    # package_audit
    "stage.package_audit.audit",
    "stage.package_audit.triage",
    "stage.package_audit.fix",
    "stage.package_audit.validation",
    # documentation
    "stage.documentation.decision_review",
    "stage.documentation.task_decompose",
    "stage.documentation.scribe",
    # codebase_migration
    "stage.codebase_migration.mapping",
    "stage.codebase_migration.audit",
    "stage.codebase_migration.fix",
    "stage.codebase_migration.validation",
    # sync_context
    "stage.sync_context.sync",
}

# Regex that matches float representations of OCEAN scores
_OCEAN_FLOAT_PATTERN = re.compile(
    r"\b(Openness|Conscientiousness|Extraversion|Agreeableness|Neuroticism)\s*=\s*\d+\.\d+",
    re.IGNORECASE,
)


################
#   CHECKS
################


def check_personas_no_floats() -> list[str]:
    """Verify no persona renders raw OCEAN float scores."""
    errors: list[str] = []
    for key, persona in PERSONA_REGISTRY.items():
        rendered = persona.get_system_instructions()
        match = _OCEAN_FLOAT_PATTERN.search(rendered)
        if match:
            errors.append(
                f"[FAIL] Persona '{key}' renders OCEAN float: '{match.group()}'. "
                "Use natural-language descriptors instead."
            )
    return errors


def check_reasoning_keys() -> list[str]:
    """Verify all 4 reasoning-mode keys exist in PROMPT_REGISTRY."""
    errors: list[str] = []
    for key in EXPECTED_REASONING_KEYS:
        if key not in PROMPT_REGISTRY:
            errors.append(f"[FAIL] Missing reasoning key in PROMPT_REGISTRY: '{key}'")
        elif not PROMPT_REGISTRY[key].strip():
            errors.append(f"[FAIL] Reasoning key '{key}' is empty.")
    return errors


def check_stage_keys() -> list[str]:
    """Verify all 29 workflow-stage keys exist and are non-empty in PROMPT_REGISTRY."""
    errors: list[str] = []
    for key in EXPECTED_STAGE_KEYS:
        if key not in PROMPT_REGISTRY:
            errors.append(f"[FAIL] Missing stage key in PROMPT_REGISTRY: '{key}'")
        elif not PROMPT_REGISTRY[key].strip():
            errors.append(f"[FAIL] Stage key '{key}' is empty.")
    return errors


################
#   MAIN
################


def main() -> int:
    """Run all caching compliance checks. Return 0 on pass, 1 on failure."""
    all_errors: list[str] = []

    print("=== Prompt Caching Compliance Check ===\n")

    print("[1/3] Checking persona rendering (no OCEAN floats)...")
    errs = check_personas_no_floats()
    all_errors.extend(errs)
    if not errs:
        print(f"  ✓ All {len(PERSONA_REGISTRY)} personas render without OCEAN floats.\n")
    else:
        for e in errs:
            print(f"  {e}")
        print()

    print("[2/3] Checking reasoning-mode keys in PROMPT_REGISTRY...")
    errs = check_reasoning_keys()
    all_errors.extend(errs)
    if not errs:
        print(f"  ✓ All {len(EXPECTED_REASONING_KEYS)} reasoning-mode keys present.\n")
    else:
        for e in errs:
            print(f"  {e}")
        print()

    print("[3/3] Checking workflow-stage keys in PROMPT_REGISTRY...")
    errs = check_stage_keys()
    all_errors.extend(errs)
    if not errs:
        print(f"  ✓ All {len(EXPECTED_STAGE_KEYS)} stage keys present.\n")
    else:
        for e in errs:
            print(f"  {e}")
        print()

    if all_errors:
        print(f"RESULT: {len(all_errors)} compliance issue(s) found.")
        return 1

    print("RESULT: All checks passed. Prompt system is caching-compliant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
