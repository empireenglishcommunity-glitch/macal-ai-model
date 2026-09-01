"""The pending queue — the mechanism behind "input is never lost" (R11.2).

When every brain is unavailable the turn is not dropped and it is not failed: it
is written here, acknowledged to the owner, and processed on recovery. The
distinction matters more than it looks. A message the owner *believes* was
received but which vanished is worse than an outright error, because he will not
send it again.

Durability rules, each with a reason:

* **Append then flush then fsync.** A container kill must not lose the item; this
  file is the only record that the owner said something.
* **Claim by rewrite, not by delete.** Draining rewrites the file atomically
  (write a temporary, then rename) so a crash mid-drain leaves either the old
  file or the new one, never a truncated one that would parse as a shorter queue.
* **A malformed line is kept, not skipped.** It is surfaced as an item with
  ``_malformed`` so it can be inspected. Silently discarding what cannot be parsed
  is how "input is never lost" quietly becomes false.

This is a file rather than a table because the SQLite spine arrives in task 1.5.
It is deliberately a shape that survives that migration: the queue is drained, not
queried.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vizier.clock import to_stamp, utcnow


class QueueError(Exception):
    """The queue could not be written. The caller must not claim success."""


class PendingQueue:
    """A durable FIFO of turns waiting for a brain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def push(self, payload: Mapping[str, Any], *, reason: str) -> None:
        """Append one pending turn.

        Raises :class:`QueueError` on failure. A caller that swallows this and
        tells the owner "queued" has lied to him.
        """
        item = {
            "queued_at": to_stamp(utcnow()),
            "reason": reason,
            "payload": dict(payload),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise QueueError(f"cannot write to queue {self.path}: {exc}") from exc

    def peek(self) -> list[dict[str, Any]]:
        """Every pending item, oldest first, without claiming any."""
        if not self.path.is_file():
            return []
        items: list[dict[str, Any]] = []
        for number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                items.append({"_malformed": True, "_line": number, "_raw": raw[:200]})
                continue
            items.append(parsed)
        return items

    def depth(self) -> int:
        return len(self.peek())

    def drain(self) -> list[dict[str, Any]]:
        """Claim and return every pending item, emptying the queue atomically.

        Write-then-rename means a crash during the drain leaves the queue intact
        rather than half-consumed. The trade-off is honest and stated: if the
        process dies *after* the rename but *before* the caller finishes
        processing, those items are lost from the queue. That is why the caller
        must audit each item as it is handled — at-least-once delivery is task
        7.2's business (N5), and this method is the seam it will build on.
        """
        items = self.peek()
        if not items:
            return []
        try:
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text("", encoding="utf-8")
            temporary.replace(self.path)
        except OSError as exc:
            raise QueueError(f"cannot drain queue {self.path}: {exc}") from exc
        return items
