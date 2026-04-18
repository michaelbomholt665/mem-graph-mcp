"""Load fixture-backed eval inputs from the repository test fixtures."""

from __future__ import annotations

import json
import runpy
from functools import lru_cache
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def load_code_fixtures() -> dict[str, str]:
    namespace = runpy.run_path(
        str(_repo_root() / "tests" / "fixtures" / "sample_code.py")
    )
    return {
        key: value
        for key, value in namespace.items()
        if key.isupper() and isinstance(value, str)
    }


@lru_cache(maxsize=1)
def load_violation_fixtures() -> dict[str, Any]:
    fixture_path = _repo_root() / "tests" / "fixtures" / "sample_violations.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_graph_fixtures() -> dict[str, Any]:
    fixture_path = _repo_root() / "tests" / "fixtures" / "sample_graph_data.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def format_preloaded_files(files: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"### {item['path']}\n```\n{item['content']}\n```" for item in files
    )
