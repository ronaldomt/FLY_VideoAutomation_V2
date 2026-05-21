"""Typed exceptions used across behaviors.

HTTP layer maps these to status codes. See CLAUDE.md §14.
"""

from __future__ import annotations


class FlyBackendError(Exception):
    """Base class — never raise directly."""


class BehaviorError(FlyBackendError):
    """A behavior failed in an expected way (validation, precondition)."""


class IntegrationError(FlyBackendError):
    """An external integration (Composio, ffmpeg) failed."""


class VerificationError(FlyBackendError):
    """Upload verification mismatch. Card wipe MUST NOT proceed."""


class NotConfiguredError(BehaviorError):
    """Required setting is missing (e.g., local_root unset)."""
