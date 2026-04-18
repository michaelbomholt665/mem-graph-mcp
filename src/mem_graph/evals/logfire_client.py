"""Logfire hosted dataset client helpers for evals."""

from __future__ import annotations

import os
from pathlib import Path
import json

from dotenv import load_dotenv
from logfire.experimental.api_client import AsyncLogfireAPIClient, LogfireAPIClient


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_env() -> None:
    load_dotenv(_repo_root() / ".env")


def _api_key() -> str:
    _load_env()
    token = (
        os.getenv("LOGFIRE_DATASETS_API_KEY")
        or os.getenv("LOGFIRE_DATASETS_TOKEN")
        or os.getenv("LOGFIRE_API_KEY")
    )
    if not token:
        raise RuntimeError(
            "Set LOGFIRE_DATASETS_API_KEY, LOGFIRE_DATASETS_TOKEN, "
            "or LOGFIRE_API_KEY to use hosted eval datasets. LOGFIRE_TOKEN "
            "is a project write token and cannot manage hosted datasets."
        )
    return token


def _base_url() -> str | None:
    _load_env()
    explicit = os.getenv("LOGFIRE_DATASETS_BASE_URL") or os.getenv("LOGFIRE_BASE_URL")
    if explicit:
        return explicit

    credentials_path = _repo_root() / ".logfire" / "logfire_credentials.json"
    if not credentials_path.exists():
        return None

    try:
        credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    url = credentials.get("logfire_api_url")
    return url if isinstance(url, str) and url else None


def get_client() -> LogfireAPIClient:
    """Return a synchronous Logfire API client for hosted datasets."""
    return LogfireAPIClient(api_key=_api_key(), base_url=_base_url())


def get_async_client() -> AsyncLogfireAPIClient:
    """Return an asynchronous Logfire API client for hosted datasets."""
    return AsyncLogfireAPIClient(api_key=_api_key(), base_url=_base_url())
