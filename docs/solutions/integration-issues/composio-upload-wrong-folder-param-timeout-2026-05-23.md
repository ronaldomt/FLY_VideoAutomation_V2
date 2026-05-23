---
title: "Composio GOOGLEDRIVE_UPLOAD_FILE: wrong parameter name sends files to Drive root"
date: 2026-05-23
category: docs/solutions/integration-issues/
module: composio_drive
problem_type: integration_issue
component: service_object
severity: critical
symptoms:
  - All uploaded files appear in Google Drive root instead of the target folder
  - No error raised — upload succeeds with a valid file ID but in the wrong location
  - Large video uploads (100MB+) timeout during the Composio R2-to-Drive transfer step
  - Issue reproduces silently on every upload; verified only by checking Drive destination
root_cause: wrong_api
resolution_type: code_fix
tags:
  - composio
  - google-drive
  - upload
  - parameter-name
  - timeout
  - r2
  - wrong-folder
  - googledrive-upload-file
---

# Composio GOOGLEDRIVE_UPLOAD_FILE: wrong parameter name sends files to Drive root

## Problem

The Composio `GOOGLEDRIVE_UPLOAD_FILE` action accepts a parameter called `folder_to_upload_to` to specify the destination folder in Drive. The code was passing `parent_folder_id` (wrong name), which Composio silently ignores. Every upload succeeded with a valid file ID but placed the file in Drive root instead of the target folder — with no error raised. Separately, the HTTP client had a hardcoded 60-second timeout, which was insufficient for Composio's internal R2→Drive transfer step on large video files.

## Symptoms

- All uploaded files appeared in Google Drive root regardless of what `folder_to_upload_to` was configured to be.
- The upload reported success (returned a file ID) with no exception raised.
- For large video files (100MB+), uploads timed out even though the file had already been staged to Cloudflare R2.
- The issue was reported 5+ times and persisted across multiple unrelated attempted fixes.

## What Didn't Work

- Hardening `ensure_subfolder` to raise on empty-string folder IDs — this was a separate defensive fix, not the root cause.
- Changing the guard from `if remote_parent is None` to `if not remote_parent` — same direction, missed the actual parameter name.
- Direct Google Drive API uploads using Composio's stored OAuth access token — Composio's stored token is always expired/stale. Composio only refreshes tokens internally during its own action execution; bypassing it means no valid credential exists. The approach was abandoned.

## Solution

**File: `backend/src/fly_backend/integrations/composio_drive.py`**

Change the parameter name from `parent_folder_id` to `folder_to_upload_to`, and pass an explicit `timeout=300` for upload operations:

```python
# Before (wrong — Composio silently ignores unrecognized parameters, uploads to Drive root)
result = self._exec(
    "GOOGLEDRIVE_UPLOAD_FILE",
    {
        "file_to_upload": {"name": local.name, "mimetype": mime, "s3key": s3key},
        "parent_folder_id": parent_folder_id,  # ← ignored by Composio
    },
)

# After (correct)
result = self._exec(
    "GOOGLEDRIVE_UPLOAD_FILE",
    {
        "file_to_upload": {"name": local.name, "mimetype": mime, "s3key": s3key},
        "folder_to_upload_to": parent_folder_id,  # ← correct parameter name
    },
    timeout=300,  # ← 5 minutes for large video R2→Drive transfer
)
```

**File: `backend/src/fly_backend/integrations/composio_client.py`**

Add a `timeout` parameter to `composio_execute`, defaulting to 60s for metadata operations, overridable per call:

```python
def composio_execute(
    api_key: str,
    connection_id: str,
    entity_id: str,
    action: str,
    input_params: dict[str, Any],
    timeout: int = 60,  # default retained for metadata ops
) -> dict[str, Any]:
    ...
    resp = _requests.post(
        ...,
        timeout=timeout,  # was hardcoded 60
    )
```

Also normalize response parsing to handle both Composio envelope formats:

```python
# Composio returns either {"id": "..."} or {"data": {"id": "..."}, "successful": true}
file_id: str = str(
    result.get("id") or (result.get("data") or {}).get("id") or ""
)
```

## Why This Works

Composio's action schema defines the destination parameter as `folder_to_upload_to`. When an unrecognized key (`parent_folder_id`) is passed, Composio does not error — it silently ignores it and applies the action's default behavior, which is Drive root. The fix aligns the code with the actual schema, confirmed by fetching `GET /api/v2/actions/GOOGLEDRIVE_UPLOAD_FILE` from Composio's live API.

The timeout fix addresses Composio's two-phase upload flow: the client PUTs the file to Composio's presigned Cloudflare R2 URL (fast), then Composio's backend moves the file from R2 into Drive (slow for large files). The HTTP connection stays open until the second phase completes. 60 seconds is insufficient for files above ~50MB; 300 seconds accommodates several-hundred-MB video files.

## Prevention

- **Never guess Composio parameter names.** Before implementing any new action call, fetch the live schema: `GET /api/v2/actions/<ACTION_NAME>` and confirm every parameter key. Treat the schema as the source of truth, not intuition or analogous parameter names from other APIs.
- **Set differentiated timeouts per operation type.** Metadata calls (folder resolution, listing) can keep the 60s default. Any action involving a file transfer should use at minimum 300s. Make this explicit at the call site with a named constant or argument — do not rely on a single global default.
- **Assert upload destination in integration tests.** Verify that the returned file's parent folder ID matches the intended folder, not just that a file ID was returned. A successful response with a wrong location is a silent data routing failure.
- **Parse Composio responses defensively.** Composio returns at least two envelope formats. Always normalize: `result.get("id") or (result.get("data") or {}).get("id")`.

## Related Issues

- `backend/src/fly_backend/integrations/composio_drive.py` — `_upload_via_composio`, `_exec`
- `backend/src/fly_backend/integrations/composio_client.py` — `composio_execute`
