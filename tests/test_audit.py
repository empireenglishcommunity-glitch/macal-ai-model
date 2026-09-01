"""Tests for the audit log.

The audit log is the answer to *"why did you do that?"* (R7.9), so the properties
under test are: it records everything, it never records a secret, it never
silently loses a row, and it refuses to fail quietly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vizier.clock import parse_stamp
from vizier.conscience.audit import AuditError, AuditEvent, AuditLog


def test_a_row_is_written_and_readable(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(
        AuditEvent(
            actor="telegram:1",
            action="door.inbound.accepted",
            outcome="ok",
            reason="owner message accepted",
        )
    )
    rows = log.read_all()
    assert len(rows) == 1
    assert rows[0]["action"] == "door.inbound.accepted"
    assert rows[0]["reason"] == "owner message accepted"


def test_the_log_is_append_only(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    for index in range(5):
        log.record(AuditEvent(actor="system", action=f"a{index}", outcome="ok", reason="r"))
    assert [row["action"] for row in log.read_all()] == ["a0", "a1", "a2", "a3", "a4"]


def test_every_row_carries_a_parseable_utc_stamp(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(AuditEvent(actor="system", action="a", outcome="ok", reason="r"))
    stamp = parse_stamp(log.read_all()[0]["at"])
    assert stamp is not None
    assert stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_a_reason_is_mandatory_by_construction() -> None:
    """``reason`` has no default. Forgetting it is a TypeError at the call site,
    not a row that cannot explain itself."""
    with pytest.raises(TypeError):
        AuditEvent(actor="system", action="a", outcome="ok")  # type: ignore[call-arg]


# ─── secrets must never reach the log (R7.10) ──────────────────────────────


def test_a_secret_in_the_reason_is_redacted(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    secret = "gsk_" + "a" * 40
    log.record(
        AuditEvent(actor="system", action="brain.call", outcome="ok", reason=f"used {secret}")
    )
    written = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert secret not in written
    assert "[REDACTED]" in written


def test_a_secret_nested_in_detail_is_redacted(tmp_path: Path) -> None:
    """Redaction runs on the serialised line, so a secret smuggled inside a nested
    structure is caught too — not only the fields someone remembered to guard."""
    log = AuditLog(tmp_path / "audit.jsonl")
    secret = "github_pat_" + "b" * 40
    log.record(
        AuditEvent(
            actor="system",
            action="git.push",
            outcome="ok",
            reason="pushed",
            detail={"env": {"nested": {"deeper": secret}}},
        )
    )
    written = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert secret not in written
    assert "[REDACTED]" in written


def test_redaction_does_not_break_the_json(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(
        AuditEvent(
            actor="system",
            action="a",
            outcome="ok",
            reason="token sk-" + "c" * 40,
            detail={"n": 1},
        )
    )
    line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["detail"] == {"n": 1}


# ─── failures must be loud ─────────────────────────────────────────────────


def test_an_unwritable_path_raises(tmp_path: Path) -> None:
    """No audit row means the action did not happen. Callers must not swallow this."""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    log = AuditLog(blocker / "audit.jsonl")
    with pytest.raises(AuditError):
        log.record(AuditEvent(actor="system", action="a", outcome="ok", reason="r"))


def test_parent_directories_are_created(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "deep" / "nested" / "audit.jsonl")
    log.record(AuditEvent(actor="system", action="a", outcome="ok", reason="r"))
    assert len(log.read_all()) == 1


# ─── reading must not lie ──────────────────────────────────────────────────


def test_a_malformed_line_is_surfaced_not_skipped(tmp_path: Path) -> None:
    """A parser that silently drops what it cannot read turns a log into a guess:
    the count looks plausible and the missing row is the one you needed."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.record(AuditEvent(actor="system", action="good", outcome="ok", reason="r"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{this is not json\n")

    rows = log.read_all()
    assert len(rows) == 2
    assert rows[1]["_malformed"] is True
    assert rows[1]["_line"] == 2


def test_a_missing_log_reads_as_empty_not_an_error(tmp_path: Path) -> None:
    assert AuditLog(tmp_path / "absent.jsonl").read_all() == []


def test_read_last_returns_the_most_recent_rows_oldest_first(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    for index in range(10):
        log.record(AuditEvent(actor="system", action=f"a{index}", outcome="ok", reason="r"))
    assert [row["action"] for row in log.read_last(3)] == ["a7", "a8", "a9"]
    assert log.read_last(0) == []
    assert log.read_last(-1) == []


def test_count_where_matches_on_every_given_field(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record(AuditEvent(actor="a", action="x", outcome="ok", reason="r"))
    log.record(AuditEvent(actor="a", action="x", outcome="refused", reason="r"))
    log.record(AuditEvent(actor="b", action="x", outcome="ok", reason="r"))

    assert log.count_where(action="x") == 3
    assert log.count_where(action="x", outcome="ok") == 2
    assert log.count_where(actor="a", outcome="refused") == 1
    assert log.count_where(action="nope") == 0
