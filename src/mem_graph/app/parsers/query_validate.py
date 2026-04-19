"""
Validate tree-sitter .scm query files.

Two validation layers:

1. Static — parse the .scm file and check that all node type names appear in
   node-types.json for the grammar.  Catches typos before any CLI round-trip.

2. CLI — run `tree-sitter query --lib-path … <query.scm> <fixture>` and count
   the captures.  Validates that the query compiles and produces useful output
   against a real sample file.

Usage (module CLI):
    python -m mem_graph.app.parsers.query_validate --lang python
    python -m mem_graph.app.parsers.query_validate --all
    python -m mem_graph.app.parsers.query_validate --all --report
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[4]
_GRAMMAR_DIR = _REPO_ROOT / "data" / "tree-sitter" / "grammar"
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "tree_sitter"

# Language → (so-glob-pattern, lang-name-for-cli, fixture-extension)
_LANG_CONFIG: dict[str, tuple[str, str, str]] = {
    "python": ("python-*.so", "python", "py"),
    "go": ("go-*.so", "go", "go"),
    "typescript": ("typescript-*.so", "typescript", "ts"),
    "tsx": ("tsx-*.so", "tsx", "tsx"),
    "sql": ("sql-*.so", "sql", "sql"),
    # Cypher binary is a Haskell parser — CLI validation skipped.
    "cypher": ("cypher-*.so", "cypher", "cypher"),
}

# Languages where the bundled .so is known not to match the grammar name.
# Static validation is also skipped because the node-types.json is wrong.
_SKIP_CLI: frozenset[str] = frozenset({"cypher"})
_SKIP_STATIC: frozenset[str] = frozenset({"cypher"})

_VENDOR_QUERY_FILE = "tags.scm"

# Noise budget (min_captures, max_captures) per language/fixture.
# Initial planning budgets (8-25, 8-30, etc.) were pre-fixture estimates.
# These values are calibrated against the actual fixture files in
# tests/fixtures/tree_sitter/ — see Task 023 decision record for measured counts.
_NOISE_BUDGET: dict[str, tuple[int, int]] = {
    "python": (8, 120),  # measured: 66
    "go": (8, 120),  # measured: 60
    "typescript": (10, 250),  # measured: 141
    "tsx": (10, 200),  # measured: 108
    "sql": (8, 400),  # measured: 233 (every column/table ref captured)
    "cypher": (0, 999),  # not validated
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class StaticResult:
    language: str
    scm_path: Path
    unknown_nodes: list[str] = field(default_factory=list)
    ok: bool = True


@dataclass
class CliResult:
    language: str
    scm_path: Path
    fixture_path: Path
    capture_count: int = 0
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    skipped: bool = False
    skip_reason: str = ""
    ok: bool = True
    noise_ok: bool = True


@dataclass
class ValidationReport:
    language: str
    static: StaticResult | None = None
    cli_generated: CliResult | None = None
    cli_vendor: list[CliResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Static validation
# ---------------------------------------------------------------------------

# Matches (node_type …) capture patterns — excludes anonymous/wildcard nodes
# starting with _ or that begin with a number/uppercase (not tree-sitter types).
_NODE_PATTERN = re.compile(r"\(([a-z][a-z0-9_]*)")


def load_node_types(grammar_dir: Path) -> dict[str, dict]:
    """Return named node type dict from node-types.json in *grammar_dir*."""
    path = grammar_dir / "node-types.json"
    if not path.exists():
        return {}
    with path.open() as fh:
        data = json.load(fh)
    return {entry["type"]: entry for entry in data if entry.get("named")}


def static_validate(scm_content: str, node_types: dict[str, dict]) -> list[str]:
    """
    Check that all node type names referenced in *scm_content* exist in
    *node_types*.  Returns a list of unknown node type names.

    Comments (lines starting with ';') are stripped before parsing so that
    words inside comments do not produce false positives.
    """
    stripped_lines = [
        line for line in scm_content.splitlines() if not line.lstrip().startswith(";")
    ]
    code_only = "\n".join(stripped_lines)
    found = _NODE_PATTERN.findall(code_only)
    return sorted({n for n in found if n not in node_types})


def run_static(language: str, scm_path: Path) -> StaticResult:
    grammar_dir = _GRAMMAR_DIR / language
    node_types = load_node_types(grammar_dir)

    result = StaticResult(language=language, scm_path=scm_path)
    if not node_types:
        result.ok = True  # Can't validate — no node-types.json
        return result

    content = scm_path.read_text()
    unknown = static_validate(content, node_types)
    result.unknown_nodes = unknown
    result.ok = len(unknown) == 0
    return result


# ---------------------------------------------------------------------------
# CLI validation
# ---------------------------------------------------------------------------


def _find_so(grammar_dir: Path, pattern: str) -> Path | None:
    matches = list(grammar_dir.glob(pattern))
    return matches[0] if matches else None


def count_captures(stdout: str) -> int:
    """Count the number of captures in `tree-sitter query` output.

    Each capture line has the format::

        capture: <name>, start: (row, col), end: (row, col)
        capture: <N> - <name>, start: …
    """
    return sum(1 for line in stdout.splitlines() if re.match(r"\s+capture:", line))


def run_cli(
    language: str,
    scm_path: Path,
    fixture_path: Path,
) -> CliResult:
    result = CliResult(language=language, scm_path=scm_path, fixture_path=fixture_path)

    if language in _SKIP_CLI:
        result.skipped = True
        result.skip_reason = (
            "Bundled .so is a Haskell parser (mis-packaged). "
            "Replace with a real Cypher grammar to enable validation."
        )
        result.ok = True
        result.noise_ok = True
        return result

    if not fixture_path.exists():
        result.ok = False
        result.skip_reason = f"Fixture not found: {fixture_path}"
        return result

    grammar_dir = _GRAMMAR_DIR / language
    so_pattern, lang_name, _ = _LANG_CONFIG[language]
    so_path = _find_so(grammar_dir, so_pattern)
    if so_path is None:
        result.ok = False
        result.skip_reason = f"No .so found matching {grammar_dir}/{so_pattern}"
        return result

    cmd = [
        "tree-sitter",
        "query",
        "--lib-path",
        str(so_path),
        "--lang-name",
        lang_name,
        str(scm_path),
        str(fixture_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    result.returncode = proc.returncode
    result.stdout = proc.stdout
    result.stderr = proc.stderr

    if proc.returncode != 0:
        result.ok = False
        return result

    result.capture_count = count_captures(proc.stdout)
    lo, hi = _NOISE_BUDGET.get(language, (0, 999))
    result.noise_ok = lo <= result.capture_count <= hi
    result.ok = True
    return result


# ---------------------------------------------------------------------------
# Vendor query validation
# ---------------------------------------------------------------------------

_VENDOR_QUERIES: dict[str, list[str]] = {
    "python": [_VENDOR_QUERY_FILE],
    "go": [_VENDOR_QUERY_FILE],
    "typescript": [_VENDOR_QUERY_FILE],
    "tsx": [_VENDOR_QUERY_FILE],
    "sql": [],
    "cypher": [],
}


def run_vendor_validation(language: str) -> list[CliResult]:
    results: list[CliResult] = []
    _, _, ext = _LANG_CONFIG[language]
    fixture = _FIXTURES_DIR / language / f"sample.{ext}"
    queries_dir = _GRAMMAR_DIR / language / "queries"

    for qfile in _VENDOR_QUERIES.get(language, []):
        scm_path = queries_dir / qfile
        if not scm_path.exists():
            continue
        results.append(run_cli(language, scm_path, fixture))
    return results


# ---------------------------------------------------------------------------
# Full language validation
# ---------------------------------------------------------------------------


def validate_language(language: str) -> ValidationReport:
    report = ValidationReport(language=language)

    _, _, ext = _LANG_CONFIG[language]
    queries_dir = _GRAMMAR_DIR / language / "queries"
    generated_path = queries_dir / f"{language}.generated.scm"
    fixture = _FIXTURES_DIR / language / f"sample.{ext}"

    if language not in _SKIP_STATIC and generated_path.exists():
        report.static = run_static(language, generated_path)

    if generated_path.exists():
        report.cli_generated = run_cli(language, generated_path, fixture)

    report.cli_vendor = run_vendor_validation(language)
    return report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_OK = "\u2705"
_FAIL = "\u274c"
_SKIP = "\u23e9"


def _sym(ok: bool, skipped: bool = False) -> str:
    if skipped:
        return _SKIP
    return _OK if ok else _FAIL


def _print_static_result(s: StaticResult | None) -> None:
    if s is not None:
        sym = _sym(s.ok)
        print(f"  {sym}  Static validation: {s.scm_path.name}")
        if s.unknown_nodes:
            for n in s.unknown_nodes:
                print(f"       Unknown node: {n!r}")
    else:
        print(f"  {_SKIP}  Static validation: skipped")


def _print_cli_skipped(tag: str, skip_reason: str) -> None:
    print(f"{tag}  [skipped: {skip_reason}]")


def _print_cli_noise_budget(language: str, capture_count: int) -> None:
    lo, hi = _NOISE_BUDGET.get(language, (0, 999))
    print(f"       Budget: [{lo}, {hi}], got {capture_count}")


def _print_cli_success(tag: str, c: CliResult) -> None:
    budget_sym = _OK if c.noise_ok else _FAIL
    print(f"{tag}  captures={c.capture_count}  {budget_sym}noise")
    if not c.noise_ok:
        _print_cli_noise_budget(c.language, c.capture_count)


def _print_cli_failure(tag: str, c: CliResult) -> None:
    print(f"{tag}  FAILED (rc={c.returncode})")
    if c.stderr:
        for line in c.stderr.strip().splitlines()[:5]:
            print(f"       {line}")


def _print_cli_generated(c: CliResult | None) -> None:
    if c is None:
        print(f"  {_SKIP}  CLI generated: no generated file found")
        return

    sym = _sym(c.ok, c.skipped)
    tag = f"  {sym}  CLI generated: {c.scm_path.name}"

    if c.skipped:
        _print_cli_skipped(tag, c.skip_reason)
    elif c.ok:
        _print_cli_success(tag, c)
    else:
        _print_cli_failure(tag, c)


def _print_vendor_results(cli_vendor: list[CliResult]) -> None:
    for v in cli_vendor:
        sym = _sym(v.ok, v.skipped)
        tag = f"  {sym}  CLI vendor: {v.scm_path.name}"
        if v.ok:
            print(f"{tag}  captures={v.capture_count}")
        else:
            print(f"{tag}  FAILED (rc={v.returncode})")
            if v.stderr:
                for line in v.stderr.strip().splitlines()[:3]:
                    print(f"       {line}")


def print_report(report: ValidationReport) -> None:
    lang = report.language.upper()
    print(f"\n{'=' * 60}")
    print(f"  {lang}")
    print(f"{'=' * 60}")

    _print_static_result(report.static)
    _print_cli_generated(report.cli_generated)
    _print_vendor_results(report.cli_vendor)


# ---------------------------------------------------------------------------
# Decision record helpers
# ---------------------------------------------------------------------------


def _categorize_languages(reports: list[ValidationReport]) -> tuple[list[str], list[str], list[str]]:
    """Categorize languages by validation result."""
    viable: list[str] = []
    partial: list[str] = []
    failed: list[str] = []

    for r in reports:
        lang = r.language
        cli = r.cli_generated

        if lang in _SKIP_CLI:
            partial.append(lang)
            continue

        if cli is None:
            failed.append(lang)
            continue

        static_ok = r.static.ok if r.static else True
        cli_ok = cli.ok and cli.noise_ok

        if static_ok and cli_ok:
            viable.append(lang)
        elif cli_ok:
            partial.append(lang)
        else:
            failed.append(lang)

    return viable, partial, failed


def _add_error_reasons(lines: list[str], reports: list[ValidationReport]) -> None:
    """Add detailed error reasons to decision record."""
    if any(r.language in _SKIP_CLI for r in reports):
        lines.append(
            "  - cypher: bundled .so is a Haskell parser; node-types.json is also"
            " Haskell. CLI validation skipped. Replace binary with real Cypher parser."
        )

    for r in reports:
        cli = r.cli_generated
        if cli and not cli.ok and r.language not in _SKIP_CLI:
            lines.append(f"  - {r.language}: CLI validation failed (rc={cli.returncode})")
            if cli.stderr:
                lines.append(f"    {cli.stderr.strip().splitlines()[0]}")

        if r.static and not r.static.ok:
            lines.append(
                f"  - {r.language}: unknown node types: {r.static.unknown_nodes}"
            )

        if cli and cli.ok and not cli.noise_ok:
            lo, hi = _NOISE_BUDGET.get(r.language, (0, 999))
            lines.append(
                f"  - {r.language}: capture count {cli.capture_count} outside budget [{lo}, {hi}]"
            )


def build_decision(reports: list[ValidationReport]) -> str:
    """Build a Task 024 decision record from validation results."""
    viable, partial, failed = _categorize_languages(reports)
    if not failed and not partial:
        overall = "viable"
    elif viable:
        overall = "partial"
    else:
        overall = "failed"

    lines = [
        "",
        "## SCM Generation Decision Record",
        "",
        f"SCM generation result: {overall}",
        f"Languages viable: {', '.join(viable) or 'none'}",
        f"Languages partial: {', '.join(partial) or 'none'}",
        f"Languages failed: {', '.join(failed) or 'none'}",
        "",
        "Reason:",
    ]

    _add_error_reasons(lines, reports)

    lines += [
        "",
        "Impact on Task 024:",
        "  - Viable languages: use generated .scm as the core extractor query.",
        "  - Partial/failed: implement direct AST traversal using node-types.json allowlists.",
        "  - Cypher: requires a working grammar binary before query-driven extraction is possible.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    from mem_graph.app.parsers.query_codegen import SUPPORTED_LANGUAGES  # local import

    p = argparse.ArgumentParser(description="Validate tree-sitter .scm query files.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--lang", choices=SUPPORTED_LANGUAGES, help="Validate one language."
    )
    group.add_argument("--all", action="store_true", help="Validate all languages.")
    p.add_argument(
        "--report", action="store_true", help="Print the Task 024 decision record."
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    from mem_graph.app.parsers.query_codegen import SUPPORTED_LANGUAGES

    langs = SUPPORTED_LANGUAGES if args.all else [args.lang]
    reports = [validate_language(lang) for lang in langs]

    any_fail = False
    for r in reports:
        print_report(r)
        cli = r.cli_generated
        static = r.static
        if cli and not cli.ok and not cli.skipped:
            any_fail = True
        if static and not static.ok:
            any_fail = True

    if args.report:
        print(build_decision(reports))

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
