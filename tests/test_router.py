"""Tests for the router and the pending queue.

These are the tests for requirement R11 — "degrades instead of breaking". The
scenario that matters most is :func:`test_when_every_brain_is_down_the_input_is_queued_not_lost`:
a message the owner *believes* was received but which vanished is worse than an
outright error, because he will not send it again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vizier.brains.base import (
    BrainAuthError,
    BrainError,
    BrainRefusedError,
    BrainReply,
    BrainRequest,
    BrainUnavailableError,
    Message,
    RateLimitedError,
)
from vizier.conscience.audit import AuditLog
from vizier.core.queue import PendingQueue, QueueError
from vizier.core.router import Router, UnknownTierError

ASK = BrainRequest(messages=[Message(role="user", content="hello")])
CHAIN = {"thinking": ("thinking", "reflex", "private"), "private": ("private",)}


class FakeBrain:
    """A brain that answers, or raises whatever it was told to."""

    def __init__(self, name: str, *, fails: Exception | None = None) -> None:
        self._name = name
        self._fails = fails
        self.calls = 0

    @property
    def provider(self) -> str:
        return f"provider-{self._name}"

    @property
    def model(self) -> str:
        return f"model-{self._name}"

    def complete(self, request: BrainRequest) -> BrainReply:
        self.calls += 1
        if self._fails is not None:
            raise self._fails
        return BrainReply(
            text=f"answer from {self._name}", provider=self.provider, model=self.model
        )


def build(
    tmp_path: Path, brains: dict[str, FakeBrain], *, with_queue: bool = True
) -> tuple[Router, AuditLog, PendingQueue]:
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = PendingQueue(tmp_path / "queue.jsonl")
    router = Router(brains, CHAIN, audit, queue=queue if with_queue else None)
    return router, audit, queue


# ─── the happy path, and provenance ────────────────────────────────────────


def test_the_first_healthy_tier_answers(tmp_path: Path) -> None:
    brains = {"thinking": FakeBrain("thinking"), "reflex": FakeBrain("reflex")}
    router, audit, _ = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    assert result.ok
    assert result.answered_by == "thinking"
    assert brains["reflex"].calls == 0, "a healthy first tier must not touch the fallback"
    assert audit.count_where(action="brain.call", outcome="ok") == 1


def test_the_result_reports_which_brain_answered(tmp_path: Path) -> None:
    """R11.1: the owner must be able to ask "which brain was that?"."""
    brains = {
        "thinking": FakeBrain("thinking", fails=RateLimitedError("quota")),
        "reflex": FakeBrain("reflex"),
    }
    router, _, _ = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    assert result.answered_by == "reflex"
    assert result.summary() == "answered by reflex [thinking:rate_limited -> reflex:ok]"


# ─── falling through (R11.3) ────────────────────────────────────────────────


def test_rate_limiting_costs_a_fallback_never_a_turn(tmp_path: Path) -> None:
    """On a free tier this is a NORMAL operating condition, not an incident."""
    brains = {
        "thinking": FakeBrain("thinking", fails=RateLimitedError("quota", retry_after_seconds=5)),
        "reflex": FakeBrain("reflex"),
    }
    router, _, _ = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    assert result.ok
    assert result.reply is not None and "reflex" in result.reply.text


def test_transport_failure_falls_through(tmp_path: Path) -> None:
    brains = {
        "thinking": FakeBrain("thinking", fails=BrainUnavailableError("no network")),
        "reflex": FakeBrain("reflex"),
    }
    router, _, _ = build(tmp_path, brains)
    assert router.ask("thinking", ASK).answered_by == "reflex"


def test_an_unclassified_brain_error_is_treated_as_transient(tmp_path: Path) -> None:
    """An adapter leaking an unknown BrainError must not cost the owner an answer,
    but the audit must say the ADAPTER is at fault, not the provider."""
    brains = {
        "thinking": FakeBrain("thinking", fails=BrainError("something odd")),
        "reflex": FakeBrain("reflex"),
    }
    router, audit, _ = build(tmp_path, brains)

    assert router.ask("thinking", ASK).answered_by == "reflex"
    reasons = " ".join(str(row.get("reason", "")) for row in audit.read_all())
    assert "unclassified" in reasons


def test_a_credential_failure_falls_through_but_is_loud(tmp_path: Path) -> None:
    """The owner still gets an answer, but a rotated key must not silently demote
    every turn to the weakest brain forever."""
    brains = {
        "thinking": FakeBrain("thinking", fails=BrainAuthError("401")),
        "reflex": FakeBrain("reflex"),
    }
    router, audit, _ = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    assert result.answered_by == "reflex"
    rows = [row for row in audit.read_all() if row.get("blast") == "RED"]
    assert len(rows) == 1
    assert "CREDENTIAL REJECTED" in str(rows[0]["reason"])


def test_a_bad_request_stops_the_chain_immediately(tmp_path: Path) -> None:
    """Retrying a malformed request everywhere turns one clear error into four
    confusing ones and burns the quota the fallback exists to protect."""
    brains = {
        "thinking": FakeBrain("thinking", fails=BrainRefusedError("too long")),
        "reflex": FakeBrain("reflex"),
    }
    router, _, queue = build(tmp_path, brains)

    result = router.ask("thinking", ASK, queue_payload={"text": "hello"})

    assert not result.ok
    assert result.queued is False, "a bad request must not be queued for retry"
    assert brains["reflex"].calls == 0
    assert queue.depth() == 0


def test_a_tier_declared_in_the_chain_but_not_enabled_is_recorded_as_skipped(
    tmp_path: Path,
) -> None:
    """A chain that quietly has one live link is a chain with no redundancy, and
    the operator should be able to see that from the trail."""
    brains = {"thinking": FakeBrain("thinking", fails=BrainUnavailableError("down"))}
    router, _, _ = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    outcomes = [(a.tier, a.outcome) for a in result.attempts]
    assert outcomes == [
        ("thinking", "unavailable"),
        ("reflex", "skipped"),
        ("private", "skipped"),
    ]


# ─── input is never lost (R11.2) ────────────────────────────────────────────


def test_when_every_brain_is_down_the_input_is_queued_not_lost(tmp_path: Path) -> None:
    """The load-bearing test for R11.2."""
    brains = {
        "thinking": FakeBrain("thinking", fails=BrainUnavailableError("down")),
        "reflex": FakeBrain("reflex", fails=BrainUnavailableError("down")),
        "private": FakeBrain("private", fails=BrainUnavailableError("pc is off")),
    }
    router, audit, queue = build(tmp_path, brains)

    result = router.ask("thinking", ASK, queue_payload={"chat_id": 1, "text": "remember this"})

    assert not result.ok
    assert result.queued is True
    assert result.summary() == "queued: every configured brain was unavailable"

    pending = queue.peek()
    assert len(pending) == 1
    assert pending[0]["payload"]["text"] == "remember this"
    assert audit.count_where(action="brain.exhausted", outcome="queued") == 1


def test_without_a_payload_the_caller_gets_a_plain_failure(tmp_path: Path) -> None:
    """Passing queue_payload is how a caller opts INTO the guarantee. Omitting it
    must not silently store a half-formed item."""
    brains = {"thinking": FakeBrain("thinking", fails=BrainUnavailableError("down"))}
    router, audit, queue = build(tmp_path, brains)

    result = router.ask("thinking", ASK)

    assert result.queued is False
    assert queue.depth() == 0
    assert audit.count_where(action="brain.exhausted", outcome="error") == 1


def test_with_no_queue_configured_nothing_is_claimed_to_be_queued(tmp_path: Path) -> None:
    brains = {"thinking": FakeBrain("thinking", fails=BrainUnavailableError("down"))}
    router, _, _ = build(tmp_path, brains, with_queue=False)
    assert router.ask("thinking", ASK, queue_payload={"x": 1}).queued is False


def test_an_unknown_tier_is_a_programming_error_not_a_silent_default(tmp_path: Path) -> None:
    router, _, _ = build(tmp_path, {"thinking": FakeBrain("thinking")})
    with pytest.raises(UnknownTierError, match="ghost"):
        router.ask("ghost", ASK)


# ─── the queue itself ──────────────────────────────────────────────────────


def test_the_queue_survives_a_restart(tmp_path: Path) -> None:
    PendingQueue(tmp_path / "q.jsonl").push({"text": "a"}, reason="brains down")
    assert PendingQueue(tmp_path / "q.jsonl").depth() == 1


def test_draining_empties_the_queue_and_returns_everything(tmp_path: Path) -> None:
    queue = PendingQueue(tmp_path / "q.jsonl")
    for index in range(3):
        queue.push({"n": index}, reason="r")

    drained = queue.drain()

    assert [item["payload"]["n"] for item in drained] == [0, 1, 2]
    assert queue.depth() == 0
    assert queue.drain() == []


def test_draining_leaves_no_temporary_file(tmp_path: Path) -> None:
    """Write-then-rename: a crash mid-drain must leave the queue intact rather
    than half-consumed."""
    queue = PendingQueue(tmp_path / "q.jsonl")
    queue.push({"n": 1}, reason="r")
    queue.drain()
    assert list(tmp_path.glob("*.tmp")) == []


def test_every_queued_item_records_when_and_why(tmp_path: Path) -> None:
    queue = PendingQueue(tmp_path / "q.jsonl")
    queue.push({"n": 1}, reason="all brains unavailable")
    item = queue.peek()[0]
    assert item["reason"] == "all brains unavailable"
    assert item["queued_at"].endswith("+0000")


def test_a_malformed_queue_line_is_kept_not_discarded(tmp_path: Path) -> None:
    """Silently discarding what cannot be parsed is how "input is never lost"
    quietly becomes false."""
    path = tmp_path / "q.jsonl"
    queue = PendingQueue(path)
    queue.push({"n": 1}, reason="r")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    items = queue.peek()
    assert len(items) == 2
    assert items[1]["_malformed"] is True


def test_a_missing_queue_file_is_empty_not_an_error(tmp_path: Path) -> None:
    assert PendingQueue(tmp_path / "absent.jsonl").peek() == []


def test_an_unwritable_queue_raises_rather_than_lying(tmp_path: Path) -> None:
    """A caller that swallows this and tells the owner "queued" has lied to him."""
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not a directory", encoding="utf-8")
    with pytest.raises(QueueError):
        PendingQueue(blocker / "q.jsonl").push({"n": 1}, reason="r")
