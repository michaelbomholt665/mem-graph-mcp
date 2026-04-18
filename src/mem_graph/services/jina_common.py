"""Shared models and utilities for Jina/code semantic linking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
MAX_FILE_BYTES = 64_000
MAX_FILE_CHARS = 8_000
DEFAULT_TIMEOUT_SECONDS = 15.0
DONE_STATUSES = {"closed", "done", "resolved"}
LANGUAGE_BY_SUFFIX = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".md": "markdown",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class JinaConfigurationError(RuntimeError):
    """Raised when Jina access is requested without required configuration."""


class JinaIssue(BaseModel):
    """A Jina issue payload normalized for semantic matching."""

    key: str = Field(description="Issue key, for example MEM-42.")
    title: str = Field(description="Short Jina issue summary.")
    description: str = Field(default="", description="Flattened issue description.")
    status: str = Field(default="Unknown", description="Current Jina workflow state.")
    assignee: str | None = Field(default=None, description="Display name of the current assignee.")
    created_at: datetime | None = Field(default=None, description="Original creation timestamp.")
    url: str = Field(description="Browsable issue URL.")

    def issue_id(self) -> str:
        return jina_issue_id(self.key)

    def as_embedding_text(self) -> str:
        return f"{self.key}\n{self.title}\n{self.description}".strip()


class CodeMatch(BaseModel):
    """A semantic match between a Jina issue and a code file."""

    file_id: str
    file_path: str
    absolute_path: str
    language: str
    score: float
    relation: str
    snippet: str


class TicketMatch(BaseModel):
    """A semantic match between a code file and a Jina issue."""

    issue_id: str
    key: str
    title: str
    status: str
    assignee: str | None = None
    url: str
    score: float
    relation: str


@dataclass(slots=True)
class IndexedCodeFile:
    """In-memory representation of an indexed file used for scoring and snippets."""

    file_id: str
    absolute_path: str
    relative_path: str
    language: str
    size_bytes: int
    content_hash: str
    summary: str
    content: str
    embedding: list[float]


def jina_issue_id(issue_key: str) -> str:
    return f"jina:{issue_key.strip().upper()}"


def code_file_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"codefile:{digest}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def bool_has_value(value: str | None) -> bool:
    return bool(value and value.strip())


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def flatten_description(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(part for part in (flatten_description(item) for item in value) if part)
    if isinstance(value, dict):
        node_type = str(value.get("type", ""))
        if node_type == "text":
            return str(value.get("text", ""))
        if node_type == "hardBreak":
            return "\n"
        content = flatten_description(value.get("content"))
        if node_type in {"paragraph", "heading", "bulletList", "orderedList", "listItem"}:
            return content.strip()
        return content.strip()
    return str(value).strip()


def language_for_path(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def summarize_content(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return " ".join(lines[:3])[:220]


def extract_snippet(issue: JinaIssue, content: str, *, context_lines: int = 3) -> str:
    tokens = {
        token.lower()
        for token in (issue.title + " " + issue.description).replace("-", " ").split()
        if len(token) >= 4
    }
    lines = content.splitlines()
    for index, line in enumerate(lines):
        lowered = line.lower()
        if any(token in lowered for token in tokens):
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            return "\n".join(lines[start:end]).strip()
    return "\n".join(lines[: min(len(lines), context_lines * 2 + 1)]).strip()

