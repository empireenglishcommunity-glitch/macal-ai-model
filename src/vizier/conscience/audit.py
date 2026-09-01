"""The audit log: append-only, redacted, and load-bearing.

Two requirements make this module unusual, and both are deliberate:

* **R7.8** — *every* action, attempted or refused, writes a row.
* **R7.9** — the Vizier must always be able to answer *"why did you do that?"*
  from this log alone.

So :meth:`AuditLog.record` **raises** if it cannot write, and callers must not
swallow that. A system that keeps acting after its audit trail breaks is a system
whose history is a guess. This ecosystem has already learned the shape of that
failure the hard way: a broad ``except ... : continue`` swallowed a ``TypeError``
and an alert was unable to fire for six weeks with nothing reporting it. Silence
looked exactly like "nothing to report".

Rows are JSON Lines: greppable with no tooling, appendable with no locking, and
readable by a human with ``tail``. The SQLite audit table in task 1.4 is built
*from* this file rather than replacing it, so the durable record never depends on
a schema migration.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from vizier.clock import to_stamp, utcnow
from vizier.config import redact

#: Blast classes (design.md D7). ``BLACK`` is refused unconditionally; it still
#: gets a row, because a refused attempt is exactly the thing worth knowing about.
Blast = Literal["GREEN", "YELLOW", "RED", "BLACK"]

#: Outcome of an attempt. ``queued`` matters: it is how "the brains were all down
#: but your input was not lost" is distinguished from "nothing happened" (R11.2).
Outcome = Literal["ok", "refused", "error", "queued", "draft", "expired"]

MINISTRY_NONE: Final[str] = "none"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One thing that happened, with the reason it happened.

    ``reason`` is not decoration. It is the field that makes R7.9 answerable, and
    the precedent is direct: the reminder system here was only reviewable once
    ``nudge_decision()`` returned a logged REASON rather than just a verdict.
    """

    actor: str
    action: str
    outcome: Outcome
    reason: str
    ministry: str = MINISTRY_NONE
    blast: Blast = "GREEN"
    autonomy: str = "L0"
    detail: Mapping[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: to_stamp(utcnow()))

    def to_json_line(self) -> str:
        """Serialise, then redact the *serialised* form.

        Redacting the whole line rather than each field is deliberate: a secret
        that arrives inside a nested ``detail`` value, or inside ``reason``, is
        still caught. Redacting per-field would only protect the fields someone
        remembered to protect.
        """
        payload = {
            "at": self.at,
            "actor": self.actor,
            "ministry": self.ministry,
            "action": self.action,
            "blast": self.blast,
            "autonomy": self.autonomy,
            "outcome": self.outcome,
            "reason": self.reason,
            "detail": self.detail,
        }
        return redact(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


class AuditError(Exception):
    """The audit log could not be written. Do not continue past this."""


class AuditLog:
    """Append-only JSON Lines audit trail."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, event: AuditEvent) -> None:
        """Append one row, flushed to disk before returning.

        Raises :class:`AuditError` on any failure. Callers must let it propagate:
        no audit row means the action did not happen.
        """
        line = event.to_json_line()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Line-buffered append. fsync so a container kill cannot lose the row
            # that explains what the process was doing when it died.
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise AuditError(f"cannot write audit row to {self.path}: {exc}") from exc

    def read_all(self) -> list[dict[str, Any]]:
        """Every row, oldest first. Malformed lines are surfaced, not skipped.

        A parser that silently drops what it cannot read is how a log stops being
        evidence: the count looks plausible and the missing row is the one you
        needed.
        """
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                rows.append({"_malformed": True, "_line": number, "_raw": raw[:200]})
                continue
            rows.append(parsed)
        return rows

    def read_last(self, count: int) -> list[dict[str, Any]]:
        """The most recent ``count`` rows, oldest first."""
        if count <= 0:
            return []
        return self.read_all()[-count:]

    def count_where(self, **criteria: str) -> int:
        """Rows matching every given field exactly.

        Exists so a verification step can assert a number rather than eyeball a
        log — e.g. "exactly one refusal row for that stranger, and zero brain
        calls".
        """
        matched = 0
        for row in self.read_all():
            if all(row.get(key) == value for key, value in criteria.items()):
                matched += 1
        return matched
