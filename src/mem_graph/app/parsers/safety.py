"""
safety.py — Parse / index limits, deadline counters, and leak diagnostics.

Must not own: business logic or DB access.
"""

from __future__ import annotations

import resource
import threading
import time
from dataclasses import dataclass, field

from .types import ParseLimits

# ---------------------------------------------------------------------------
# Execution context (one per parse/extract call)
# ---------------------------------------------------------------------------


@dataclass
class SafetyContext:
    """Tracks counters and enforces limits for one parse/extract/resolve call."""

    limits: ParseLimits
    _started_at: float = field(default_factory=time.monotonic, init=False)
    _nodes_visited: int = field(default=0, init=False)
    _captures_processed: int = field(default=0, init=False)
    _symbols_extracted: int = field(default=0, init=False)
    _edges_extracted: int = field(default=0, init=False)
    _resolver_passes: int = field(default=0, init=False)
    limit_hit: str | None = field(default=None, init=False)

    # ----------------------------------------------------------------
    # Increment counters — return False when limit exceeded
    # ----------------------------------------------------------------

    def inc_nodes(self, n: int = 1) -> bool:
        self._nodes_visited += n
        if self._nodes_visited > self.limits.max_nodes_visited:
            self.limit_hit = f"nodes_visited>{self.limits.max_nodes_visited}"
            return False
        return True

    def inc_captures(self, n: int = 1) -> bool:
        self._captures_processed += n
        if self._captures_processed > self.limits.max_captures:
            self.limit_hit = f"captures>{self.limits.max_captures}"
            return False
        return True

    def inc_symbols(self, n: int = 1) -> bool:
        self._symbols_extracted += n
        if self._symbols_extracted > self.limits.max_symbols:
            self.limit_hit = f"symbols>{self.limits.max_symbols}"
            return False
        return True

    def inc_edges(self, n: int = 1) -> bool:
        self._edges_extracted += n
        if self._edges_extracted > self.limits.max_edges:
            self.limit_hit = f"edges>{self.limits.max_edges}"
            return False
        return True

    def inc_resolver_passes(self) -> bool:
        self._resolver_passes += 1
        if self._resolver_passes > self.limits.max_resolver_passes:
            self.limit_hit = f"resolver_passes>{self.limits.max_resolver_passes}"
            return False
        return True

    def check_deadline(self) -> bool:
        elapsed_ms = (time.monotonic() - self._started_at) * 1000
        if elapsed_ms > self.limits.max_parse_ms:
            self.limit_hit = f"parse_ms>{self.limits.max_parse_ms}"
            return False
        return True

    # ----------------------------------------------------------------
    # Diagnostics
    # ----------------------------------------------------------------

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._started_at) * 1000

    @property
    def nodes_visited(self) -> int:
        return self._nodes_visited

    @property
    def captures_processed(self) -> int:
        return self._captures_processed

    @property
    def symbols_extracted(self) -> int:
        return self._symbols_extracted

    @property
    def edges_extracted(self) -> int:
        return self._edges_extracted


# ---------------------------------------------------------------------------
# File-size check (before any parsing)
# ---------------------------------------------------------------------------


def check_file_size(content: bytes, limits: ParseLimits) -> str | None:
    """Return an error string if the file exceeds the size limit, else None."""
    if len(content) > limits.max_file_bytes:
        return f"file_size {len(content)} > max {limits.max_file_bytes}"
    return None


# ---------------------------------------------------------------------------
# Leak diagnostics (for safety tests — no-op in production)
# ---------------------------------------------------------------------------


@dataclass
class LeakSnapshot:
    """Process-level metrics captured before/after a parse loop."""

    rss_bytes: int
    fd_count: int
    thread_count: int

    @classmethod
    def capture(cls) -> "LeakSnapshot":
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in KB on Linux
        rss = usage.ru_maxrss * 1024
        try:
            import os

            fd_dir = f"/proc/{os.getpid()}/fd"
            fds = len(list(__import__("pathlib").Path(fd_dir).iterdir()))
        except Exception:
            fds = -1
        threads = threading.active_count()
        return cls(rss_bytes=rss, fd_count=fds, thread_count=threads)

    def delta(self, other: "LeakSnapshot") -> dict[str, int]:
        return {
            "rss_delta_bytes": other.rss_bytes - self.rss_bytes,
            "fd_delta": other.fd_count - self.fd_count,
            "thread_delta": other.thread_count - self.thread_count,
        }
