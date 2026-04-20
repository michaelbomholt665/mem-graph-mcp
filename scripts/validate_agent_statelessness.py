#!/usr/bin/env python3
# scripts/validate_agent_statelessness.py
"""
Validate that no agent module accumulates state on ctx by monkey-patching.

Walks all agent source files and checks that no line attempts to set
attributes on a RunContext instance (ctx._something = ...). This is the
canonical form of the forbidden pattern.

Exit 0 = clean. Exit 1 = violations found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_AGENTS_ROOT = Path(__file__).parent.parent / "src" / "mem_graph" / "agents"

# Pattern: ctx._identifier = ... (whitespace-flexible)
_CTX_MONKEY_PATCH = re.compile(r"\bctx\._\w+\s*=\s*")

# Pattern: getattr(ctx, "_...")  — reading a monkey-patched attribute
_CTX_GETATTR = re.compile(r"\bgetattr\s*\(\s*ctx\s*,\s*[\"']_")

# Pattern: hasattr(ctx, "_...")  — lazily initialising on ctx
_CTX_HASATTR = re.compile(r"\bhasattr\s*\(\s*ctx\s*,\s*[\"']_")


def _check_file(path: Path) -> list[str]:
    """Return list of violation descriptions for a single file."""
    violations: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        # Skip comment lines and lines that start with string markers
        # They may contain example code in docstrings.
        if stripped.startswith(("#", '"""', "'''", "``")):
            continue
        if _CTX_MONKEY_PATCH.search(line):
            violations.append(f"{path}:{lineno}: ctx monkey-patch: {line.strip()!r}")
        if _CTX_GETATTR.search(line):
            violations.append(f"{path}:{lineno}: ctx getattr(_): {line.strip()!r}")
        if _CTX_HASATTR.search(line):
            violations.append(f"{path}:{lineno}: ctx hasattr(_): {line.strip()!r}")
    return violations


def main() -> int:
    agent_files = list(_AGENTS_ROOT.rglob("*.py"))
    if not agent_files:
        print(f"ERROR: No Python files found under {_AGENTS_ROOT}", file=sys.stderr)
        return 1

    all_violations: list[str] = []
    for path in sorted(agent_files):
        all_violations.extend(_check_file(path))

    if all_violations:
        print("Agent statelessness check FAILED:\n")
        for v in all_violations:
            print(f"  {v}")
        print(
            f"\n{len(all_violations)} violation(s) found in {len(agent_files)} files.\n"
            "State MUST live in deps dataclass fields, not on RunContext.\n"
            "Example: `ctx.deps._my_state.append(x)` — NOT `ctx._my_state = []`."
        )
        return 1

    print(
        f"Agent statelessness check PASSED — {len(agent_files)} file(s) scanned, "
        "no ctx monkey-patching found."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
