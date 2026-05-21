"""Per-launch shared-secret auth.

Every non-health request must carry `X-Sidecar-Token: <token>`. The token is
generated at startup and written alongside the port in the runtime file.

See CLAUDE.md §10.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

TOKEN_HEADER = "X-Sidecar-Token"


class SidecarAuth:
    """Holds the per-launch token. Mutable so tests can override."""

    def __init__(self, token: str) -> None:
        self.token = token

    def verify(self, request: Request) -> None:
        # `/health` is exempt: shell hits it before reading the runtime file.
        if request.url.path == "/health":
            return
        provided = request.headers.get(TOKEN_HEADER, "")
        if not hmac.compare_digest(provided, self.token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_sidecar_token",
            )
