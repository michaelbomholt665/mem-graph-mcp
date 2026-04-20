#!/usr/bin/env python3
# src/mem_graph/services/audit/fingerprint.py
"""
Deterministic deduplication service for audit findings.

Computes stable SHA-256 fingerprints for AuditFindings so that the same
logical violation produces the same fingerprint across multiple audit runs,
even when surrounding code is reformatted or line numbers shift.
"""

from __future__ import annotations

################
#   IMPORTS
################

import hashlib
import re

from ...models.audit import AuditFinding

################
#   CONSTANTS
################

_WHITESPACE_RE = re.compile(r"\s+")
_COMMENT_PY_RE = re.compile(r"#.*$", re.MULTILINE)
_COMMENT_GO_RE = re.compile(r"//.*$", re.MULTILINE)
_COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

################
#   PUBLIC API
################


def fingerprint_compute_hash(finding: AuditFinding) -> str:
    """
    Compute a stable SHA-256 fingerprint for an audit finding.

    The fingerprint is derived from file_path + rule_id + normalized_snippet
    so that cosmetic changes (whitespace reformatting, comment edits) do not
    produce new fingerprints for the same logical violation.

    Args:
        finding: The AuditFinding to fingerprint.

    Returns:
        A 16-character hex string (first 64 bits of SHA-256).
    """
    normalised = _fingerprint_normalise_snippet(finding.code_snippet or "")
    raw = f"{finding.file_path}::{finding.rule_id}::{normalised}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest[:16]


def fingerprint_attach_to_findings(findings: list[AuditFinding]) -> list[AuditFinding]:
    """
    Attach a computed fingerprint to each finding in-place.

    Mutates the fingerprint field on each AuditFinding and returns the
    same list for convenience. Safe to call multiple times — idempotent.

    Args:
        findings: List of AuditFindings to fingerprint.

    Returns:
        The same list with fingerprint fields populated.
    """
    for finding in findings:
        finding.fingerprint = fingerprint_compute_hash(finding)
    return findings


################
#   HELPERS
################


def _fingerprint_normalise_snippet(snippet: str) -> str:
    """
    Normalise a code snippet for stable hashing.

    Strips single-line comments (Python/Go/JS style), block comments,
    all whitespace runs, and leading/trailing space. The result is a
    compact token string suitable for stable fingerprinting.

    Args:
        snippet: Raw code snippet from the finding.

    Returns:
        Normalised string with comments and whitespace stripped.
    """
    text = snippet
    text = _COMMENT_BLOCK_RE.sub("", text)
    text = _COMMENT_PY_RE.sub("", text)
    text = _COMMENT_GO_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()
