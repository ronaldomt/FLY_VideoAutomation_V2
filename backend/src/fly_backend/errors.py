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


class ConcurrencyLimitError(BehaviorError):
    """Another session is already running and `settings.session_concurrency`
    is reached. The HTTP layer maps this to ``409 session_concurrency_limit``.
    V1 scope says "one session at a time per workstation"; the cap is
    configurable so v2 can lift it without code changes.
    """
