"""mem_graph package.

Agent memory MCP server, graph models, agent implementations, and
supporting services for the Syntx memory workspace.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
import tomllib


def _read_project_version() -> str | None:
	pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
	if not pyproject_path.is_file():
		return None
	with pyproject_path.open("rb") as pyproject_file:
		project_data = tomllib.load(pyproject_file)
	version_value = project_data.get("project", {}).get("version")
	return version_value if isinstance(version_value, str) else None


def _resolve_version() -> str:
	project_version = _read_project_version()
	if project_version is not None:
		return project_version
	try:
		return package_version("memory")
	except PackageNotFoundError as exc:
		raise RuntimeError("Could not resolve the mem_graph package version") from exc


__version__ = _resolve_version()

__all__ = ["__version__"]
