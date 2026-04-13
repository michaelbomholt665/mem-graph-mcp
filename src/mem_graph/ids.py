#!/usr/bin/env python3
# src/mem_graph/ids.py
"""
ids.py — Canonical ID generation for mem-graph.

All graph nodes must use ``id_generate_v7()`` as their primary key.
UUIDv7 strings are lexicographically sortable by creation time,
closing the gap between the documented data-model contract and the
previous ``uuid.uuid4()`` implementation.
"""

from __future__ import annotations

import uuid_utils as _uu


def id_generate_v7() -> str:
    """Return a new UUIDv7 string (time-ordered, URL-safe, 36 chars)."""
    return str(_uu.uuid7())
