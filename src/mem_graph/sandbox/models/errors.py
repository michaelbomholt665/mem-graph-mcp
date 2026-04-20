"""Typed exceptions for sandbox operations."""

from __future__ import annotations


class SandboxError(RuntimeError):
    """Base class for sandbox failures."""


class SandboxDisabledError(SandboxError):
    """Raised when a sandbox operation requires the disabled backend."""


class SandboxNotFoundError(SandboxError):
    """Raised when a session cannot be found."""


class SandboxProvisionError(SandboxError):
    """Raised when container provisioning fails."""


class SandboxExecutionError(SandboxError):
    """Raised when execution cannot be started."""


class SandboxPolicyError(SandboxError):
    """Raised when an operation violates sandbox policy."""


class SandboxMergeConflictError(SandboxError):
    """Raised when merge-back would overwrite host changes."""
