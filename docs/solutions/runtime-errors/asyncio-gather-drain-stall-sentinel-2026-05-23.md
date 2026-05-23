---
title: "asyncio.gather without return_exceptions=True causes SSE upload stream to stall permanently"
date: 2026-05-23
category: docs/solutions/runtime-errors/
module: behaviors/upload_to_drive
problem_type: runtime_error
component: tooling
severity: high
symptoms:
  - Upload progress bar freezes at last completed file and never advances
  - SSE stream stays open indefinitely — no further events reach the frontend
  - Session remains in running state permanently; never reaches failed or completed
  - No error is surfaced to the operator despite an upload task having raised
root_cause: async_timing
resolution_type: code_fix
tags:
  - asyncio
  - gather
  - sse
  - sentinel
  - upload
  - concurrency
  - stall
  - return-exceptions
---

# asyncio.gather without return_exceptions=True causes SSE upload stream to stall permanently

## Problem

In the upload handler's `_drain` coroutine, `asyncio.gather(*tasks)` was called without `return_exceptions=True`. If any upload task raised an exception, `gather` propagated it immediately, causing `_drain` to exit before placing the sentinel in the queue. The consumer loop then waited on `queue.get()` forever, freezing the SSE stream and leaving the session in a permanent `running` state.

## Symptoms

- Upload progress bar freezes at the last successfully reported file and never completes.
- The SSE connection stays open indefinitely with no further events.
- The session page shows no error — the session appears to still be running.
- The freeze is most reliably triggered when the last file in the upload batch fails (e.g., timeout), but any task exception reproduces it.

## What Didn't Work

No alternative approaches were documented for this specific issue — the bug was identified directly from the control flow. Any workaround that did not guarantee sentinel delivery under all exit paths would reproduce the freeze.

## Solution

**File: `backend/src/fly_backend/behaviors/upload_to_drive/handler.py`**

Use `return_exceptions=True` in `asyncio.gather` so the sentinel is always placed in the queue before any exception propagates:

```python
# Before — gather raises on first task failure, sentinel never sent
async def _drain() -> None:
    await asyncio.gather(*tasks)       # raises on first task failure
    await queue.put(_SENTINEL)         # never reached if gather raises

# After — sentinel always sent, exception re-raised after
async def _drain() -> None:
    results = await asyncio.gather(*tasks, return_exceptions=True)  # never raises
    await queue.put(_SENTINEL)   # always reached regardless of task outcomes
    for r in results:            # re-raise first exception after sentinel is queued
        if isinstance(r, BaseException):
            raise r
```

The consumer loop:

```python
while True:
    event = await queue.get()
    if event is _SENTINEL:
        break
    yield event
```

Now always receives the sentinel and exits. The re-raised exception propagates through `await drainer` in the `finally` block, which correctly marks the session as failed.

## Why This Works

`asyncio.gather` with the default `return_exceptions=False` immediately propagates the first exception it encounters, aborting its own execution. Code after the `await asyncio.gather(...)` line — including `queue.put(_SENTINEL)` — is skipped. The consumer coroutine blocks on `await queue.get()` indefinitely because the sentinel that would break its loop was never produced.

With `return_exceptions=True`, `gather` always completes and returns a list. Failed tasks appear as exception instances in the list rather than being raised. The sentinel is guaranteed to reach the queue. The loop breaks, the SSE stream closes cleanly, and the exception is re-raised in the expected place so the session failure path executes normally.

## Prevention

- **Never place cleanup or signaling code after a bare `await asyncio.gather()`** when those tasks can fail. The pattern "run tasks, then signal done" requires `return_exceptions=True` or a `try/finally` around the gather — otherwise any task failure silently skips the signal.
- **Guarantee sentinel delivery under all exit paths.** For any producer-consumer queue that uses a sentinel for termination, ask: is there a code path that skips `queue.put(_SENTINEL)`? If yes, move it into a `finally` block or use `return_exceptions=True`.
- **Add an SSE watchdog test.** Inject a failing upload task, then assert that the SSE stream closes within a bounded time (e.g., 5 seconds) and that the session reaches `failed` state rather than hanging. This directly catches this regression.
- **Default to `return_exceptions=True` in background worker gather calls.** Silent hangs are harder to diagnose than explicit exceptions. Collect all results, then iterate and re-raise. Reserve `return_exceptions=False` for cases where fail-fast is explicitly desired and the calling context handles it.

## Related Issues

- `backend/src/fly_backend/behaviors/upload_to_drive/handler.py` — `_drain`, consumer loop
