#!/usr/bin/env python3
"""CLI entry point for mem-graph eval suites."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from mem_graph.evals.evaluator import main


if __name__ == "__main__":
    raise SystemExit(main())