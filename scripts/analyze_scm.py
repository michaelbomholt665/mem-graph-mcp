#!/usr/bin/env python3
# scripts/analyze_scm.py
"""
SCM capture analyzer.

Reads one or more .scm query files and reports:
  - Every capture name found
  - The NodeKind it maps to (using the same logic as scm.py)
  - Estimated node count per kind
  - Estimated edge count (structural + semantic)
  - A per-language summary table

Default (no args) — auto-discovers all languages under:
    data/tree-sitter/grammar/{language}/queries/{language}.scm
    (resolved relative to this script's parent directory)

Usage:
    python scripts/analyze_scm.py
    python scripts/analyze_scm.py go python typescript tsx
    python scripts/analyze_scm.py path/to/custom.scm
"""

################
#   IMPORTS
################

import re
import sys
from collections import defaultdict
from pathlib import Path


################
#   CONSTANTS
################

# Mirror of _CAPTURE_KIND_MAP from scm.py
CAPTURE_KIND_MAP: dict[str, str] = {
    "name.definition.function":  "FUNCTION",
    "name.definition.method":    "METHOD",
    "name.definition.class":     "CLASS",
    "name.definition.interface": "INTERFACE",
    "name.definition.module":    "MODULE",
    "name.definition.type":      "TYPE",
    "name.definition.macro":     "FUNCTION",
    "name.definition.constant":  "CONSTANT",
    "name.definition.field":     "VARIABLE",
    "name.definition.enum":      "ENUM",
    "name.definition.struct":    "STRUCT",
    "name.definition.namespace": "MODULE",
    "definition.function":       "FUNCTION",
    "definition.method":         "METHOD",
    "definition.class":          "CLASS",
    "definition.interface":      "INTERFACE",
    "definition.type":           "TYPE",
    "definition.struct":         "STRUCT",
    "definition.enum":           "ENUM",
}

# Captures that produce semantic edges (calls, imports, type refs)
SEMANTIC_EDGE_CAPTURES: set[str] = {
    "call.site", "call.target", "call.receiver",
    "import.statement", "import.module",
    "reference.call", "reference.type", "reference.class",
}

# Captures that are pure noise (syntax highlighting, not graph-relevant)
NOISE_CAPTURES: set[str] = {
    "operator", "keyword", "string", "number", "comment",
    "escape", "punctuation", "punctuation.bracket",
    "punctuation.special", "constant.builtin", "type.builtin",
    "embedded",
}

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
DIM    = "\033[2m"


################
#   PARSING
################

def extract_captures(scm_text: str) -> list[str]:
    """
    Extract all @capture_name tokens from a .scm file.

    Strips comments and returns the raw capture names in order,
    including duplicates (since the same name can appear many times).
    """
    lines = [
        line for line in scm_text.splitlines()
        if not line.strip().startswith(";")
    ]
    clean = "\n".join(lines)
    return re.findall(r"@([\w.]+)", clean)


################
#   CLASSIFICATION
################

def kind_from_capture(capture_name: str) -> str:
    """
    Map a capture name to a NodeKind string.

    Mirrors the logic in scm.py _kind_from_capture exactly so results
    are comparable to what the real extractor produces.
    """
    for prefix, kind in CAPTURE_KIND_MAP.items():
        if capture_name == prefix or capture_name.endswith(f".{prefix}"):
            return kind

    if "function" in capture_name:
        return "FUNCTION"
    if "class" in capture_name or "type" in capture_name:
        return "CLASS"
    if "method" in capture_name:
        return "METHOD"
    if "import" in capture_name:
        return "IMPORT"

    return "ELEMENT"


def classify_capture(capture_name: str) -> str:
    """
    Classify a capture as: symbol | semantic_edge | noise | other.

    Used to bucket captures into meaningful reporting categories.
    """
    base = capture_name.split(".")[-1]
    root = capture_name.split(".")[0]

    if root in NOISE_CAPTURES or base in NOISE_CAPTURES:
        return "noise"

    if capture_name in SEMANTIC_EDGE_CAPTURES:
        return "semantic_edge"
    for sem in SEMANTIC_EDGE_CAPTURES:
        if capture_name.startswith(sem) or capture_name.endswith(sem):
            return "semantic_edge"

    if "symbol" in capture_name or "definition" in capture_name:
        return "symbol"

    if any(k in capture_name for k in ("call", "import", "reference")):
        return "semantic_edge"

    return "other"


################
#   ANALYSIS
################

def analyze_scm(path: Path) -> dict:
    """
    Analyze a single .scm file and return a structured result dict.

    Returns capture breakdown, kind counts, edge estimates, and
    the full list of unique captures with their classifications.
    """
    text = path.read_text(encoding="utf-8")
    all_captures = extract_captures(text)
    unique_captures = dict.fromkeys(all_captures)  # preserve order, dedupe

    kind_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    capture_details: list[dict] = []

    for capture in unique_captures:
        kind = kind_from_capture(capture)
        category = classify_capture(capture)
        kind_counts[kind] += 1
        category_counts[category] += 1
        capture_details.append({
            "capture": capture,
            "kind": kind,
            "category": category,
        })

    symbol_captures = [c for c in capture_details if c["category"] == "symbol"]
    semantic_captures = [c for c in capture_details if c["category"] == "semantic_edge"]

    structural_edges = len(symbol_captures) * 2  # file->symbol + contains
    semantic_edges = len(semantic_captures)

    return {
        "language": path.stem,
        "total_captures": len(all_captures),
        "unique_captures": len(unique_captures),
        "kind_counts": dict(kind_counts),
        "category_counts": dict(category_counts),
        "capture_details": capture_details,
        "symbol_captures": symbol_captures,
        "semantic_captures": semantic_captures,
        "estimated_nodes": len(symbol_captures) + 1,  # +1 for file node
        "estimated_structural_edges": structural_edges,
        "estimated_semantic_edges": semantic_edges,
        "estimated_total_edges": structural_edges + semantic_edges,
    }


################
#   DISPLAY
################

def _col(text: str, width: int, color: str = "") -> str:
    """Left-pad a string to a fixed column width with optional color."""
    cell = str(text).ljust(width)
    return f"{color}{cell}{RESET}" if color else cell


def print_language_report(result: dict) -> None:
    """Print a detailed per-language breakdown to stdout."""
    lang = result["language"].upper()
    print(f"\n{BOLD}{CYAN}{'━' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {lang}{RESET}")
    print(f"{CYAN}{'━' * 60}{RESET}")

    print(f"\n  {BOLD}Capture counts{RESET}")
    print(f"  {'Total captures (with duplicates)':<38} {result['total_captures']}")
    print(f"  {'Unique capture names':<38} {result['unique_captures']}")

    print(f"\n  {BOLD}Category breakdown{RESET}")
    cats = result["category_counts"]
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        color = GREEN if cat == "symbol" else YELLOW if cat == "semantic_edge" else RED if cat == "noise" else DIM
        bar = "█" * count
        print(f"  {_col(cat, 18, color)} {count:>3}  {color}{bar}{RESET}")

    print(f"\n  {BOLD}Symbol captures -> NodeKind{RESET}")
    if result["symbol_captures"]:
        for c in result["symbol_captures"]:
            print(f"  {DIM}@{_col(c['capture'], 42)}{RESET} -> {GREEN}{c['kind']}{RESET}")
    else:
        print(f"  {DIM}(none){RESET}")

    print(f"\n  {BOLD}Semantic edge captures{RESET}")
    if result["semantic_captures"]:
        for c in result["semantic_captures"]:
            print(f"  {DIM}@{_col(c['capture'], 42)}{RESET} -> {YELLOW}edge{RESET}")
    else:
        print(f"  {DIM}(none){RESET}")

    print(f"\n  {BOLD}Estimates (per average file){RESET}")
    print(f"  {'Nodes (symbol captures + file)':<38} ~{result['estimated_nodes']}")
    print(f"  {'Structural edges (file->sym + contains)':<38} ~{result['estimated_structural_edges']}")
    print(f"  {'Semantic edges (calls, imports, refs)':<38} ~{result['estimated_semantic_edges']}")
    print(f"  {BOLD}{'Total edges':<38} ~{result['estimated_total_edges']}{RESET}")

    ratio = (
        round(result["estimated_total_edges"] / result["estimated_nodes"], 1)
        if result["estimated_nodes"] > 0 else 0
    )
    color = GREEN if ratio >= 2 else YELLOW if ratio >= 1 else RED
    print(f"  {BOLD}{'Edge/node ratio':<38} {color}{ratio}x{RESET}")


def print_summary_table(results: list[dict]) -> None:
    """Print a compact cross-language comparison table."""
    print(f"\n{BOLD}{'━' * 72}{RESET}")
    print(f"{BOLD}  SUMMARY ACROSS ALL LANGUAGES{RESET}")
    print(f"{'━' * 72}{RESET}")

    header = (
        f"  {'Language':<14}"
        f"{'Unique cap.':<13}"
        f"{'Symbols':<10}"
        f"{'Sem.edges':<12}"
        f"{'~Nodes':<9}"
        f"{'~Edges':<9}"
        f"{'Ratio':<7}"
    )
    print(f"\n{BOLD}{header}{RESET}")
    print(f"  {'─' * 68}")

    for r in results:
        ratio = (
            round(r["estimated_total_edges"] / r["estimated_nodes"], 1)
            if r["estimated_nodes"] > 0 else 0
        )
        color = GREEN if ratio >= 2 else YELLOW if ratio >= 1 else RED
        noise = r["category_counts"].get("noise", 0)
        noise_pct = round(noise / r["unique_captures"] * 100) if r["unique_captures"] else 0

        print(
            f"  {_col(r['language'].upper(), 14, BOLD)}"
            f"{_col(r['unique_captures'], 13)}"
            f"{_col(len(r['symbol_captures']), 10, GREEN)}"
            f"{_col(len(r['semantic_captures']), 12, YELLOW)}"
            f"{_col(r['estimated_nodes'], 9)}"
            f"{_col(r['estimated_total_edges'], 9)}"
            f"{color}{ratio}x{RESET}  "
            f"{DIM}({noise_pct}% noise){RESET}"
        )

    print(f"\n  {DIM}Noise = operators, keywords, strings, comments -- no graph value{RESET}")
    print(f"  {DIM}Estimates assume each capture fires once per file (real files will be higher){RESET}\n")


################
#   PATH HELPERS
################

def _grammar_root() -> Path:
    """
    Resolve the grammar root relative to this script's location.

    Assumes the script lives at <project_root>/scripts/analyze_scm.py
    and grammars live at <project_root>/data/tree-sitter/grammar/.
    """
    return Path(__file__).parent.parent / "data" / "tree-sitter" / "grammar"


def _scm_path_for_language(language: str) -> Path:
    """Build the canonical .scm path for a given language name."""
    return _grammar_root() / language / "queries" / f"{language}.scm"


def _discover_all_languages() -> list[Path]:
    """
    Auto-discover all languages that have a canonical .scm file.

    Walks grammar root and returns sorted paths for every language
    that has the expected queries/{language}.scm file present.
    """
    root = _grammar_root()
    if not root.is_dir():
        return []
    found = []
    for lang_dir in sorted(root.iterdir()):
        if lang_dir.is_dir():
            candidate = _scm_path_for_language(lang_dir.name)
            if candidate.exists():
                found.append(candidate)
    return found


def _resolve_args(args: list[str]) -> tuple[list[Path], list[str]]:
    """
    Resolve CLI args to .scm paths.

    Each arg can be:
      - A language name (e.g. 'go')  -> data/tree-sitter/grammar/go/queries/go.scm
      - A direct .scm path           -> used as-is
    Returns (valid_paths, error_messages).
    """
    valid: list[Path] = []
    errors: list[str] = []

    for arg in args:
        p = Path(arg)
        if p.suffix == ".scm":
            if p.exists():
                valid.append(p)
            else:
                errors.append(f"File not found: {p}")
        else:
            canonical = _scm_path_for_language(arg)
            if canonical.exists():
                valid.append(canonical)
            else:
                errors.append(
                    f"Language '{arg}' not found -- expected: {canonical}"
                )

    return valid, errors


################
#   ENTRYPOINT
################

def main() -> None:
    """
    Parse CLI args, resolve .scm paths, and print per-language reports.

    With no args, auto-discovers all languages under the grammar root.
    With args, accepts language names (e.g. 'go') or direct .scm paths.
    Exits with code 1 if no valid files are found.
    """
    args = sys.argv[1:]

    if not args:
        valid = _discover_all_languages()
        if not valid:
            root = _grammar_root()
            print(
                f"{RED}No .scm files found under {root}{RESET}\n"
                f"Expected: data/tree-sitter/grammar/{{language}}/queries/{{language}}.scm",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"{DIM}Auto-discovered {len(valid)} language(s) from grammar root{RESET}")
    else:
        valid, errors = _resolve_args(args)
        for err in errors:
            print(f"{RED}{err}{RESET}", file=sys.stderr)
        if not valid:
            print(f"{RED}No valid .scm files found.{RESET}", file=sys.stderr)
            sys.exit(1)

    results = [analyze_scm(p) for p in valid]

    for result in results:
        print_language_report(result)

    if len(results) > 1:
        print_summary_table(results)


if __name__ == "__main__":
    main()
