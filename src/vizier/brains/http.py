"""Minimal JSON-over-HTTP helper shared by the brain adapters.

Standard library only. Two properties are deliberate:

* **The API key never appears in an exception message.** Adapters pass it as a
  header, and every error raised here names the status and the host, never the
  request. A stack trace is the easiest place in a system to leak a credential
  (R7.10).
* **Status codes are translated once**, here, so every adapter agrees on what a
  429 or a 401 means. An adapter that invents its own mapping is an adapter whose
  failures the router cannot reason about.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from vizier.brains.base import (
    BrainAuthError,
    BrainRefusedError,
    BrainUnavailableError,
    RateLimitedError,
)


def post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 60.0,
) -> Mapping[str, Any]:
    """POST JSON and return the parsed response.

    Raises the :mod:`vizier.brains.base` exception matching the failure class, so
    the router's fallback logic is provider-independent.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise _from_status(exc) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # No network, DNS failure, connection reset, read timeout: all transient,
        # all "try the next tier". The owner's PC being off and Egyptian power
        # cuts both land here, and both are NORMAL conditions (R11.1).
        raise BrainUnavailableError(f"transport failure: {type(exc).__name__}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BrainUnavailableError("response was not JSON") from exc
    if not isinstance(parsed, dict):
        raise BrainUnavailableError("response was not a JSON object")
    return parsed


def _from_status(
    exc: urllib.error.HTTPError,
) -> BrainUnavailableError | BrainAuthError | BrainRefusedError:
    status = exc.code
    if status == 429:
        return RateLimitedError("rate limited", retry_after_seconds=_retry_after(exc))
    if status in (401, 403):
        # Not "unavailable": this will not fix itself and must be visible.
        return BrainAuthError(f"credential rejected (HTTP {status})")
    if status in (400, 413, 422):
        # The next provider will refuse the same request. Do not waste the attempt.
        return BrainRefusedError(f"request rejected (HTTP {status})")
    return BrainUnavailableError(f"HTTP {status}")


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header is None:
        return None
    try:
        return float(header)
    except (TypeError, ValueError):
        return None
