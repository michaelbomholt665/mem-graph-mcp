"""Server constants and environment-derived configuration."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .. import __version__

load_dotenv()

SERVER_NAME = "syntx-memory"
SERVER_VERSION = __version__
SERVER_API_VERSION = "1.0"
SERVER_WEBSITE = os.getenv(
    "MEM_GRAPH_WEBSITE", "https://github.com/michael/syntx-memory"
)

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "9100"))
TRANSPORT = os.getenv("MCP_TRANSPORT", "http").lower()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SERVER_STARTED_AT = time.monotonic()

LAZY_NAMESPACES: frozenset[str] = frozenset(
    {
        "memory",
        "work",
        "notes",
        "audit",
        "filesystem",
        "background",
        "graph",
        "integrations",
    }
)

DEPRECATED_NAMESPACES: dict[str, str] = {
    "conversation": "memory",
    "decision": "work",
    "task": "work",
    "project": "work",
    "violation": "work",
    "note": "notes",
}

OPENAPI_SPECS: list[str] = [
    spec.strip()
    for spec in os.getenv("MEM_GRAPH_OPENAPI_SPECS", "").split(",")
    if spec.strip()
]

BANNER = r"""
__  __ ______ __  __      _____  _____            _____  _    _
  |  \/  |  ____|  \/  |    / ____|  __ \     /\    |  __ \| |  | |
  | \  / | |__  | \  / |   | |  __| |__) |   /  \   | |__) | |__| |
  | |\/| |  __| | |\/| |   | | |_ |  _  /   / /\ \  |  ___/|  __  |
  | |  | | |____| |  | |   | |__| | | \ \  / ____ \ | |    | |  | |
  |_|  |_|______|_|  |_|    \_____|_|  \_\/_/    \_\|_|    |_|  |_|

  __  __  _____ _____
 |  \/  |/ ____|  __ \
 | \  / | |    | |__) |
 | |\/| | |    |  ___/
 | |  | | |____| |
 |_|  |_|\_____|_|
"""

