"""Tests for the Telegram door.

Every test drives a fake transport, so the allowlist and reply behaviour are
verified with no token and no network. The most important test in this file is
:func:`test_a_stranger_reaches_absolutely_nothing`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from vizier.conscience.audit import AuditLog
from vizier.door.telegram import (
    MAX_POLL_BACKOFF_SECONDS,
    POLL_TICK_SECONDS,
    Allowlist,
    Door,
    InboundMessage,
    OffsetStore,
    TransportError,
    chunk_text,
    classify_update,
    detect_language,
)

OWNER = 111222333
STRANGER = 999888777


class FakeTransport:
    """Records every call. Never touches the network."""

    def __init__(self, updates: list[list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self._batches = updates or []
        self.fail_on: set[str] = set()

    #: Status attached to forced failures, so permanence can be simulated.
    fail_status: int | None = None

    def call(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((method, params))
        if method in self.fail_on:
            raise TransportError(f"{method}: forced failure", status=self.fail_status)
        if method == "getUpdates":
            batch = self._batches.pop(0) if self._batches else []
            return {"result": batch}
        return {"message_id": len(self.calls)}

    def sent_texts(self) -> list[str]:
        return [str(params["text"]) for method, params in self.calls if method == "sendMessage"]

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


class SpyHandler:
    """Stands in for the brain. Counts invocations so "zero model calls" is provable."""

    def __init__(self, reply: str = "ok") -> None:
        self.seen: list[InboundMessage] = []
        self.reply = reply
        self.raises: Exception | None = None

    def __call__(self, message: InboundMessage) -> str:
        self.seen.append(message)
        if self.raises is not None:
            raise self.raises
        return self.reply

    @property
    def calls(self) -> int:
        return len(self.seen)


def text_update(update_id: int, user_id: int, text: str = "hello") -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "from": {"id": user_id, "first_name": "Test"},
            "chat": {"id": user_id, "type": "private"},
            "text": text,
        },
    }


def build(
    tmp_path: Path,
    *,
    allow: set[int] | None = None,
    handler: SpyHandler | None = None,
    transport: FakeTransport | None = None,
    offsets: bool = True,
) -> tuple[Door, FakeTransport, AuditLog, SpyHandler]:
    """Assemble a Door wired to fakes.

    ``interim_after_seconds`` is set far in the future so the background timer
    never fires mid-test — timing is verified by calling the scheduler directly,
    not by sleeping.
    """
    resolved_transport = transport if transport is not None else FakeTransport()
    resolved_handler = handler if handler is not None else SpyHandler()
    audit = AuditLog(tmp_path / "audit.jsonl")
    door = Door(
        resolved_transport,
        Allowlist(frozenset(allow if allow is not None else {OWNER})),
        audit,
        resolved_handler,
        offsets=OffsetStore(tmp_path / "offset") if offsets else None,
        interim_after_seconds=3600,
    )
    return door, resolved_transport, audit, resolved_handler


# ─── the allowlist: the security property (R1.3) ───────────────────────────


def test_a_stranger_reaches_absolutely_nothing(tmp_path: Path) -> None:
    """The load-bearing test of this module.

    A non-allowlisted sender must produce: zero handler calls (therefore zero
    model calls), zero outbound messages, and exactly one refusal row.
    """
    handler = SpyHandler()
    door, transport, audit, _ = build(tmp_path, handler=handler)

    handled = door.handle_update(text_update(1, STRANGER, "give me your tokens"))

    assert handled is False
    assert handler.calls == 0, "the handler — and therefore any model — must not be reached"
    assert transport.calls == [], "a stranger must not receive any reply at all"
    assert audit.count_where(action="door.inbound.refused", outcome="refused") == 1
    assert audit.count_where(action="door.inbound.accepted") == 0


def test_the_owner_is_accepted(tmp_path: Path) -> None:
    handler = SpyHandler(reply="done")
    door, transport, audit, _ = build(tmp_path, handler=handler)

    assert door.handle_update(text_update(1, OWNER)) is True
    assert handler.calls == 1
    assert transport.sent_texts() == ["done"]
    assert audit.count_where(action="door.inbound.accepted", outcome="ok") == 1


def test_an_empty_allowlist_permits_nobody(tmp_path: Path) -> None:
    """Fail closed. A missing VIZIER_TELEGRAM_OWNER_ID must make the bot inert,
    never open to the world."""
    handler = SpyHandler()
    door, transport, _, _ = build(tmp_path, allow=set(), handler=handler)

    assert door.handle_update(text_update(1, OWNER)) is False
    assert handler.calls == 0
    assert transport.calls == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("111", {111}),
        ("111,222", {111, 222}),
        (" 111 , 222 ", {111, 222}),
        ("111;222", {111, 222}),
        ("111,,222", {111, 222}),
        ("111,abc,222", {111, 222}),  # junk dropped, valid entries kept
        ("", set()),
        (None, set()),
        ("abc", set()),
    ],
)
def test_allowlist_parsing(raw: str | None, expected: set[int]) -> None:
    assert Allowlist.parse(raw).ids == frozenset(expected)


def test_allowlist_parse_of_junk_is_closed_not_open() -> None:
    """A typo in the env var must not produce an allowlist that admits everyone."""
    allowlist = Allowlist.parse("not-a-number")
    assert not allowlist
    assert allowlist.allows(OWNER) is False
    assert allowlist.allows(None) is False


# ─── inbound classification (R1.2) ─────────────────────────────────────────


def test_text_message() -> None:
    message = classify_update(text_update(5, OWNER, "salam"))
    assert message is not None
    assert (message.kind, message.text, message.update_id) == ("text", "salam", 5)


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"voice": {"file_id": "v1"}}, "voice"),
        ({"audio": {"file_id": "a1"}}, "audio"),
        ({"video_note": {"file_id": "vn1"}}, "video_note"),
        ({"document": {"file_id": "d1"}}, "document"),
        ({"photo": [{"file_id": "small"}, {"file_id": "large"}]}, "photo"),
    ],
)
def test_media_kinds_are_recognised(payload: dict[str, Any], kind: str) -> None:
    update = text_update(6, OWNER)
    del update["message"]["text"]
    update["message"].update(payload)
    message = classify_update(update)
    assert message is not None
    assert message.kind == kind
    assert message.file_id is not None


def test_the_largest_photo_resolution_is_chosen() -> None:
    update = text_update(7, OWNER)
    del update["message"]["text"]
    update["message"]["photo"] = [{"file_id": "small"}, {"file_id": "medium"}, {"file_id": "large"}]
    message = classify_update(update)
    assert message is not None
    assert message.file_id == "large"


def test_a_caption_becomes_the_text_of_a_media_message() -> None:
    update = text_update(8, OWNER)
    del update["message"]["text"]
    update["message"]["document"] = {"file_id": "d1"}
    update["message"]["caption"] = "review this"
    message = classify_update(update)
    assert message is not None
    assert message.text == "review this"


def test_voice_is_flagged_for_transcription() -> None:
    update = text_update(9, OWNER)
    del update["message"]["text"]
    update["message"]["voice"] = {"file_id": "v1"}
    message = classify_update(update)
    assert message is not None
    assert message.needs_transcription is True


def test_an_edited_message_is_treated_as_a_new_one() -> None:
    """The owner correcting himself is the common case; ignoring it looks frozen."""
    update = {"update_id": 10, "edited_message": text_update(10, OWNER, "fixed")["message"]}
    message = classify_update(update)
    assert message is not None
    assert message.text == "fixed"


def test_forwarded_messages_are_marked() -> None:
    update = text_update(11, OWNER, "look at this")
    update["message"]["forward_origin"] = {"type": "user"}
    message = classify_update(update)
    assert message is not None
    assert message.is_forwarded is True


@pytest.mark.parametrize(
    "update",
    [
        {"update_id": 1},
        {"update_id": 2, "poll": {"id": "x"}},
        {"update_id": 3, "message": {"message_id": 1}},
        {"update_id": 4, "message": {"message_id": 1, "from": {"id": OWNER}}},
        {"update_id": 5, "message": "not a mapping"},
    ],
)
def test_non_actionable_updates_are_ignored(update: dict[str, Any]) -> None:
    assert classify_update(update) is None


def test_a_malformed_update_is_ignored_rather_than_crashing(tmp_path: Path) -> None:
    handler = SpyHandler()
    door, transport, _, _ = build(tmp_path, handler=handler)
    assert door.handle_update({"update_id": 1, "poll": {"id": "x"}}) is False
    assert handler.calls == 0
    assert transport.calls == []


# ─── language mirroring (R6.1) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("hello there", "en"),
        ("السلام عليكم", "ar"),
        ("check الملف please", "ar"),  # any Arabic present -> Arabic
        ("", "en"),
        ("123 !@#", "en"),
    ],
)
def test_language_detection(text: str, language: str) -> None:
    assert detect_language(text) == language


# ─── outbound chunking ─────────────────────────────────────────────────────


def test_chunking_never_loses_a_character() -> None:
    """The exact invariant. A chunker that drops a newline fails only on the one
    long message that mattered."""
    text = "\n".join(f"line {index} " + "x" * 50 for index in range(400))
    chunks = chunk_text(text, 500)
    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert all(len(chunk) <= 500 for chunk in chunks)


def test_chunking_prefers_a_newline_boundary() -> None:
    chunks = chunk_text("alpha\nbeta\ngamma", 8)
    assert "".join(chunks) == "alpha\nbeta\ngamma"
    assert chunks[0] == "alpha\n"


def test_chunking_falls_back_to_a_space_then_a_hard_cut() -> None:
    assert chunk_text("aaaa bbbb cccc", 6)[0] == "aaaa "
    unbroken = "x" * 25
    chunks = chunk_text(unbroken, 10)
    assert "".join(chunks) == unbroken
    assert [len(chunk) for chunk in chunks] == [10, 10, 5]


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("short") == ["short"]


def test_empty_text_still_produces_one_chunk() -> None:
    """R1.4: silence is a defect, so there must always be something to send."""
    assert chunk_text("") == [""]


def test_zero_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        chunk_text("x", 0)


def test_a_long_reply_is_sent_as_several_messages(tmp_path: Path) -> None:
    handler = SpyHandler(reply="y" * 9000)
    door, transport, _, _ = build(tmp_path, handler=handler)
    door.handle_update(text_update(1, OWNER))
    sent = transport.sent_texts()
    assert len(sent) == 3
    assert "".join(sent) == "y" * 9000


# ─── every accepted message gets a reply (R1.4) ────────────────────────────


def test_a_handler_exception_still_produces_a_reply(tmp_path: Path) -> None:
    handler = SpyHandler()
    handler.raises = RuntimeError("boom")
    door, transport, audit, _ = build(tmp_path, handler=handler)

    assert door.handle_update(text_update(1, OWNER)) is True
    assert len(transport.sent_texts()) == 1
    assert audit.count_where(action="door.turn.error", outcome="error") == 1


def test_an_empty_handler_reply_still_sends_something(tmp_path: Path) -> None:
    handler = SpyHandler(reply="")
    door, transport, _, _ = build(tmp_path, handler=handler)
    door.handle_update(text_update(1, OWNER))
    assert transport.sent_texts() == ["(no reply produced)"]


def test_a_typing_indicator_is_the_fast_acknowledgement(tmp_path: Path) -> None:
    handler = SpyHandler()
    door, transport, _, _ = build(tmp_path, handler=handler)
    door.handle_update(text_update(1, OWNER))
    assert transport.methods()[0] == "sendChatAction"


def test_a_failed_typing_indicator_does_not_abort_the_turn(tmp_path: Path) -> None:
    """Cosmetic failures must not cost the owner an answer."""
    handler = SpyHandler(reply="still fine")
    transport = FakeTransport()
    transport.fail_on = {"sendChatAction"}
    door, transport, _, _ = build(tmp_path, handler=handler, transport=transport)

    assert door.handle_update(text_update(1, OWNER)) is True
    assert transport.sent_texts() == ["still fine"]


def test_a_failed_real_reply_raises_rather_than_going_silent(tmp_path: Path) -> None:
    """Asymmetry on purpose: a dropped answer is indistinguishable from a dead bot."""
    handler = SpyHandler()
    transport = FakeTransport()
    transport.fail_on = {"sendMessage"}
    door, _, _, _ = build(tmp_path, handler=handler, transport=transport)

    with pytest.raises(TransportError):
        door.handle_update(text_update(1, OWNER))


# ─── polling and restart safety (R11.5) ────────────────────────────────────


def test_polling_advances_the_offset_past_every_update(tmp_path: Path) -> None:
    handler = SpyHandler()
    transport = FakeTransport([[text_update(41, OWNER), text_update(42, OWNER)]])
    door, _, _, _ = build(tmp_path, handler=handler, transport=transport)

    assert door.poll_once(0) == 43
    assert handler.calls == 2


def test_the_offset_advances_past_a_refused_update_too(tmp_path: Path) -> None:
    """Otherwise one stranger's message is re-fetched forever and the audit log
    fills with identical refusals until the disk does."""
    handler = SpyHandler()
    transport = FakeTransport([[text_update(77, STRANGER)]])
    door, _, audit, _ = build(tmp_path, handler=handler, transport=transport)

    assert door.poll_once(0) == 78
    assert handler.calls == 0
    assert audit.count_where(action="door.inbound.refused") == 1


def test_the_offset_survives_a_restart(tmp_path: Path) -> None:
    transport = FakeTransport([[text_update(500, OWNER)]])
    door, _, _, _ = build(tmp_path, transport=transport)

    door.poll_once(0)
    assert OffsetStore(tmp_path / "offset").read() == 501


def test_an_unreadable_offset_file_starts_from_zero(tmp_path: Path) -> None:
    path = tmp_path / "offset"
    path.write_text("not a number", encoding="utf-8")
    assert OffsetStore(path).read() == 0


def test_offset_writes_are_atomic(tmp_path: Path) -> None:
    """Write-then-rename: a kill mid-write must leave the old value, never a
    truncated one that would parse as a different offset."""
    store = OffsetStore(tmp_path / "offset")
    store.write(12345)
    store.write(12346)
    assert store.read() == 12346
    assert list(tmp_path.glob("*.tmp")) == []


def test_polling_stops_when_asked(tmp_path: Path) -> None:
    handler = SpyHandler()
    transport = FakeTransport([[text_update(1, OWNER)]])
    door, _, _, handler = build(tmp_path, transport=transport)

    calls = {"n": 0}

    def should_stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 2

    door.run(should_stop)
    assert handler.calls == 1


def test_a_transport_failure_while_polling_is_audited_not_fatal(tmp_path: Path) -> None:
    """Telegram being briefly unreachable is a normal condition, not an error."""
    transport = FakeTransport()
    transport.fail_on = {"getUpdates"}
    door, _, audit, _ = build(tmp_path, transport=transport)

    stop = {"n": 0}

    def should_stop() -> bool:
        stop["n"] += 1
        return stop["n"] > 2

    door.run(should_stop, wait=lambda _s, _c: None)  # must not raise
    assert audit.count_where(action="door.poll.error", outcome="error") >= 1


# ─── poll backoff: found by RUNNING the container, not by a test ────────────
#
# The first version of `Door.run` retried with no backoff and no deduplication.
# Running the image with a deliberately wrong token produced FOUR IDENTICAL audit
# rows inside one second, and would have spun at full speed forever — burning CPU
# on a 2-vCPU box shared with the students' bot and filling the disk with
# identical rows. Every unit test passed the whole time. These tests exist so it
# cannot come back.


def _run_failing(
    tmp_path: Path, *, iterations: int, status: int | None = None
) -> tuple[AuditLog, list[float]]:
    transport = FakeTransport()
    transport.fail_on = {"getUpdates"}
    transport.fail_status = status
    door, _, audit, _ = build(tmp_path, transport=transport)

    slept: list[float] = []
    counter = {"n": 0}

    def should_stop() -> bool:
        counter["n"] += 1
        return counter["n"] > iterations

    def wait(seconds: float, _should_stop: Callable[[], bool]) -> None:
        slept.append(seconds)

    door.run(should_stop, wait=wait)
    return audit, slept


def test_repeated_polling_failures_back_off_exponentially(tmp_path: Path) -> None:
    _, slept = _run_failing(tmp_path, iterations=6)
    assert slept == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]


def test_backoff_is_capped(tmp_path: Path) -> None:
    """A cap keeps the delay bounded so recovery is not needlessly slow."""
    _, slept = _run_failing(tmp_path, iterations=12)
    assert max(slept) == MAX_POLL_BACKOFF_SECONDS
    assert slept[-1] == MAX_POLL_BACKOFF_SECONDS


def test_an_identical_repeated_failure_is_counted_not_re_recorded(tmp_path: Path) -> None:
    """The actual defect: 20 identical failures must not write 20 identical rows."""
    audit, _ = _run_failing(tmp_path, iterations=20)
    assert audit.count_where(action="door.poll.error") == 1


def test_a_permanent_credential_failure_goes_straight_to_the_cap_and_is_loud(
    tmp_path: Path,
) -> None:
    """A wrong token will not fix itself. Retrying it quickly is pure waste, and
    the owner has to be told rather than left with a bot that looks alive."""
    audit, slept = _run_failing(tmp_path, iterations=3, status=401)

    assert slept == [MAX_POLL_BACKOFF_SECONDS] * 3
    rows = [row for row in audit.read_all() if row.get("action") == "door.poll.error"]
    assert len(rows) == 1
    assert rows[0]["blast"] == "RED"
    assert "REJECTED THE CREDENTIAL" in str(rows[0]["reason"])


@pytest.mark.parametrize(
    ("status", "permanent"), [(401, True), (403, True), (404, True), (500, False), (None, False)]
)
def test_permanence_classification(status: int | None, permanent: bool) -> None:
    assert TransportError("x", status=status).is_permanent is permanent


def test_recovery_is_recorded_with_the_failure_count(tmp_path: Path) -> None:
    """One summary row when it clears, so the outage is visible in the log without
    a row per attempt."""
    transport = FakeTransport([[], [text_update(1, OWNER)]])
    transport.fail_on = {"getUpdates"}
    door, _, audit, _ = build(tmp_path, transport=transport)

    counter = {"n": 0}

    def should_stop() -> bool:
        counter["n"] += 1
        if counter["n"] == 4:
            transport.fail_on = set()  # the outage clears
        return counter["n"] > 6

    door.run(should_stop, wait=lambda _s, _c: None)

    recovered = [row for row in audit.read_all() if row.get("action") == "door.poll.recovered"]
    assert len(recovered) == 1
    assert "consecutive failure(s)" in str(recovered[0]["reason"])


def test_a_healthy_loop_never_sleeps_and_never_records_a_poll_error(tmp_path: Path) -> None:
    transport = FakeTransport([[text_update(1, OWNER)]])
    door, _, audit, _ = build(tmp_path, transport=transport)

    counter = {"n": 0}
    slept: list[float] = []

    def should_stop() -> bool:
        counter["n"] += 1
        return counter["n"] > 2

    door.run(should_stop, wait=lambda seconds, _c: slept.append(seconds))

    assert slept == []
    assert audit.count_where(action="door.poll.error") == 0
    assert audit.count_where(action="door.poll.recovered") == 0


def test_the_backoff_wait_is_interruptible_so_shutdown_is_prompt() -> None:
    """A single long sleep meant SIGTERM went unnoticed for up to a minute.

    Measured on a real container: asked to stop during a backoff, it took **29
    seconds** to exit, and Docker sends SIGKILL after 10 — so a redeploy during an
    outage would kill it mid-write. The wait now returns as soon as the stop flag
    is set, and no single slice exceeds POLL_TICK_SECONDS.
    """
    assert POLL_TICK_SECONDS <= 1.0, "a slice longer than Docker's grace period defeats the point"

    stop = {"flag": False}
    started = time.monotonic()

    def should_stop() -> bool:
        # Stop is requested immediately, as a signal handler would.
        stop["flag"] = True
        return stop["flag"]

    Door._interruptible_wait(MAX_POLL_BACKOFF_SECONDS, should_stop)

    assert time.monotonic() - started < 1.5, "a requested stop must not wait out the full backoff"


def test_the_wait_actually_waits_when_not_stopping() -> None:
    """The other direction: it must not busy-spin through the backoff either."""
    started = time.monotonic()
    Door._interruptible_wait(0.05, lambda: False)
    assert time.monotonic() - started >= 0.05
