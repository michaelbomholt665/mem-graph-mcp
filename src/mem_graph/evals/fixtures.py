"""Load fixture-backed eval inputs from the repository test fixtures."""

from __future__ import annotations

import json
import os
import runpy
from functools import lru_cache
from importlib.resources import files as resource_files  # nosemgrep
from pathlib import Path
from typing import Any, Mapping


@lru_cache(maxsize=1)
def get_repo_root() -> Path:
    """Return the repository root for eval fixtures and hosted dataset helpers."""

    configured = os.getenv("MEM_GRAPH_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    package_root = Path(str(resource_files("mem_graph"))).resolve()
    for candidate in (package_root, *package_root.parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "tests" / "fixtures"
        ).exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate repository root for mem-graph eval fixtures. "
        "Set MEM_GRAPH_REPO_ROOT to override discovery."
    )


def fixture_output_for(
    outputs: Mapping[str, str],
    case_id: str,
    *,
    suite_name: str,
) -> str:
    """Return a fixture output or raise a descriptive error for missing cases."""

    if case_id not in outputs:
        available = ", ".join(sorted(outputs)) or "none"
        raise ValueError(
            f"Missing fixture output for suite '{suite_name}' case '{case_id}'. "
            f"Available cases: {available}"
        )
    return outputs[case_id]


@lru_cache(maxsize=1)
def load_code_fixtures() -> dict[str, str]:
    namespace = runpy.run_path(
        str(get_repo_root() / "tests" / "fixtures" / "sample_code.py")
    )
    return {
        key: value
        for key, value in namespace.items()
        if key.isupper() and isinstance(value, str)
    }


@lru_cache(maxsize=1)
def load_violation_fixtures() -> dict[str, Any]:
    fixture_path = get_repo_root() / "tests" / "fixtures" / "sample_violations.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_graph_fixtures() -> dict[str, Any]:
    fixture_path = get_repo_root() / "tests" / "fixtures" / "sample_graph_data.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def format_preloaded_files(files: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"### {item['path']}\n```\n{item['content']}\n```" for item in files
    )


def metadata_string(
    metadata: Mapping[str, object],
    key: str,
    *,
    suite_name: str,
    case_id: str,
    default: str | None = None,
) -> str:
    """Return a required string metadata value with a descriptive error."""

    if key in metadata:
        value = metadata[key]
    elif default is not None:
        return default
    else:
        raise ValueError(
            f"Missing metadata key '{key}' for suite '{suite_name}' case '{case_id}'."
        )

    if isinstance(value, str):
        return value

    raise ValueError(
        f"Metadata key '{key}' for suite '{suite_name}' case '{case_id}' must be a string."
    )
