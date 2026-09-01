"""The Telegram door — the only way in.

Design notes worth knowing before changing anything here (design.md D12):

* **Long-polling, not a webhook.** No inbound port, no new tunnel ingress rule, no
  public surface at all. At one user's volume a webhook buys nothing and costs an
  attack surface.
* **No third-party Telegram library.** ``urllib`` from the standard library is
  enough for one user, and every dependency is 400 MB of budget shared with ~25
  other services on a 4 GB box (N2).
* **The allowlist exists before any brain does.** This module is written in task
  1.2 and the first model adapter arrives in task 1.3, so there is no commit in
  this repository's history where an unauthenticated path could reach a model.
* **A stranger gets silence, not an error.** Replying "you are not authorised"
  confirms the bot is live and who it belongs to. Discard, audit, say nothing.

The handler is injected. In task 1.2 it is a stub; in 1.3 it becomes the brain
router. The door does not know or care which.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from vizier.conscience.audit import AuditEvent, AuditLog

#: Telegram rejects messages over 4096 characters. Chunking at 4000 leaves room
#: for the "(1/3)" style prefixes a future task may add without re-tuning this.
CHUNK_LIMIT: Final[int] = 4000

#: Ceiling for poll backoff. One minute is long enough to stop a hot loop from
#: costing CPU on a box shared with the students' bot, and short enough that the
#: owner does not notice the delay once the outage clears.
MAX_POLL_BACKOFF_SECONDS: Final[float] = 60.0

#: Longest single sleep during a backoff. Kept under Docker's default 10-second
#: stop grace period so a shutdown signal is always acted on before ``SIGKILL``.
POLL_TICK_SECONDS: Final[float] = 1.0

#: Arabic, Arabic Supplement, Extended-A, and Presentation Forms.
ARABIC_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

MessageKind = Literal["text", "voice", "audio", "photo", "document", "video_note", "unsupported"]


class Transport(Protocol):
    """The seam that makes this module testable without a network.

    Every test in ``tests/test_telegram_door.py`` drives a fake implementation, so
    the allowlist and the reply logic are verified without a token and without
    touching Telegram.
    """

    def call(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """Invoke a Bot API method. Raises :class:`TransportError` on failure."""
        ...


class TransportError(Exception):
    """The Telegram API could not be reached, or returned ``ok: false``.

    ``status`` carries the HTTP status when there was one, because the poll loop
    must distinguish "Telegram is briefly unreachable" (retry soon) from "this
    token is wrong" (retrying at speed forever achieves nothing).
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def is_permanent(self) -> bool:
        """A wrong or revoked token will not fix itself by retrying."""
        return self.status in (401, 403, 404)


class HttpTransport:
    """Bot API over HTTPS using the standard library only.

    The token is held here and **never** passed to anything else — not to the
    handler, not into an audit row, not into a log line (R7.10).
    """

    def __init__(self, token: str, *, timeout: int = 65) -> None:
        if not token.strip():
            raise ValueError("telegram token is empty")
        self._token = token.strip()
        self._timeout = timeout

    def call(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        body = json.dumps(params).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Deliberately does not include the URL: it contains the token.
            raise TransportError(f"{method}: HTTP {exc.code}", status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TransportError(f"{method}: {type(exc).__name__}") from exc

        if not isinstance(payload, dict) or not payload.get("ok"):
            description = ""
            if isinstance(payload, dict):
                description = str(payload.get("description", ""))
            raise TransportError(f"{method}: not ok {description}".strip())
        result = payload.get("result")
        return result if isinstance(result, dict) else {"result": result}


# ─────────────────────────────────────────────────────────────────────────────
# Allowlist
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Allowlist:
    """Who the Vizier obeys. Everyone else does not exist to it (R1.3)."""

    ids: frozenset[int]

    @classmethod
    def parse(cls, raw: str | None) -> Allowlist:
        """Read a comma-separated list of numeric Telegram user IDs.

        Unparseable entries are dropped rather than raising, and an empty result
        is a *valid* allowlist that permits nobody — see :meth:`allows`.
        """
        if not raw:
            return cls(frozenset())
        found: set[int] = set()
        for part in raw.replace(";", ",").split(","):
            candidate = part.strip()
            if not candidate:
                continue
            try:
                found.add(int(candidate))
            except ValueError:
                continue
        return cls(frozenset(found))

    def allows(self, user_id: int | None) -> bool:
        """Whether this user may instruct the Vizier.

        **An empty allowlist permits nobody.** This is the fail-closed direction
        and it is the opposite of the convenient one: a misconfigured or missing
        ``VIZIER_TELEGRAM_OWNER_ID`` must make the bot inert, never open. Flags and
        gates in this ecosystem fail closed by standing rule, and an allowlist is
        the most consequential gate in the system.
        """
        if user_id is None:
            return False
        return user_id in self.ids

    def __bool__(self) -> bool:
        return bool(self.ids)


# ─────────────────────────────────────────────────────────────────────────────
# Inbound normalisation
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """One owner message, normalised so the rest of the system sees one shape."""

    update_id: int
    chat_id: int
    user_id: int
    message_id: int
    kind: MessageKind
    text: str
    file_id: str | None = None
    is_forwarded: bool = False
    language: str = "en"

    @property
    def needs_transcription(self) -> bool:
        return self.kind in {"voice", "audio", "video_note"}


def detect_language(text: str) -> str:
    """``"ar"`` if the text contains Arabic script, else ``"en"``.

    Crude on purpose. The requirement (R6.1) is to *mirror* the language the owner
    wrote in, and script presence answers that exactly. A statistical detector
    would add a dependency and a new way to be confidently wrong about one word.
    """
    for char in text:
        code = ord(char)
        for start, end in ARABIC_RANGES:
            if start <= code <= end:
                return "ar"
    return "en"


def classify_update(update: Mapping[str, Any]) -> InboundMessage | None:
    """Turn a raw Telegram update into an :class:`InboundMessage`, or ``None``.

    ``None`` means "nothing here to act on" — a poll result, a chat-member change,
    a reaction. Edited messages are treated as new messages: the owner correcting
    himself is the common case and ignoring it would look like the bot froze.
    """
    raw_message = update.get("message") or update.get("edited_message")
    if not isinstance(raw_message, Mapping):
        return None

    sender = raw_message.get("from")
    chat = raw_message.get("chat")
    if not isinstance(sender, Mapping) or not isinstance(chat, Mapping):
        return None

    user_id = sender.get("id")
    chat_id = chat.get("id")
    message_id = raw_message.get("message_id")
    update_id = update.get("update_id")
    if not all(isinstance(value, int) for value in (user_id, chat_id, message_id, update_id)):
        return None

    kind: MessageKind = "unsupported"
    file_id: str | None = None
    text = ""

    if isinstance(raw_message.get("text"), str):
        kind, text = "text", raw_message["text"]
    elif isinstance(raw_message.get("voice"), Mapping):
        kind = "voice"
        file_id = _file_id(raw_message["voice"])
    elif isinstance(raw_message.get("audio"), Mapping):
        kind = "audio"
        file_id = _file_id(raw_message["audio"])
    elif isinstance(raw_message.get("video_note"), Mapping):
        kind = "video_note"
        file_id = _file_id(raw_message["video_note"])
    elif isinstance(raw_message.get("document"), Mapping):
        kind = "document"
        file_id = _file_id(raw_message["document"])
    elif isinstance(raw_message.get("photo"), list) and raw_message["photo"]:
        kind = "photo"
        # Telegram sends every resolution; the last entry is the largest.
        largest = raw_message["photo"][-1]
        file_id = _file_id(largest) if isinstance(largest, Mapping) else None

    caption = raw_message.get("caption")
    if kind != "text" and isinstance(caption, str):
        text = caption

    return InboundMessage(
        update_id=int(update_id),  # type: ignore[arg-type]
        chat_id=int(chat_id),  # type: ignore[arg-type]
        user_id=int(user_id),  # type: ignore[arg-type]
        message_id=int(message_id),  # type: ignore[arg-type]
        kind=kind,
        text=text,
        file_id=file_id,
        is_forwarded=any(
            key in raw_message for key in ("forward_origin", "forward_from", "forward_from_chat")
        ),
        language=detect_language(text),
    )


def _file_id(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("file_id")
    return value if isinstance(value, str) and value else None


# ─────────────────────────────────────────────────────────────────────────────
# Outbound
# ─────────────────────────────────────────────────────────────────────────────


def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split for Telegram's length cap **without losing a character**.

    The invariant is exact: ``"".join(chunk_text(t)) == t``. It is asserted in the
    tests, because a chunker that quietly drops a newline is the kind of defect
    that only shows up in the one long message that mattered.

    Prefers a newline boundary, then a space, then cuts hard — a hard cut is
    better than a dropped tail.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return [""]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        split_at = window.rfind("\n")
        if split_at <= 0:
            split_at = window.rfind(" ")
        if split_at <= 0:
            split_at = limit
        else:
            split_at += 1  # keep the boundary character in this chunk
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    chunks.append(remaining)
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Offset persistence
# ─────────────────────────────────────────────────────────────────────────────


class OffsetStore:
    """Remembers the last handled ``update_id`` across restarts.

    Without this, a restart replays the backlog and the owner gets every message
    answered twice — and, once hands exist, every action performed twice. Restart
    safety is requirement R11.5, and at-least-once delivery only becomes tolerable
    when the offset is durable.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> int:
        try:
            return int(self.path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            # Unknown offset means "start from whatever Telegram still holds".
            return 0

    def write(self, offset: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: a kill mid-write leaves the old value, never a
        # truncated one that would parse as a different offset.
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(str(offset), encoding="utf-8")
        temporary.replace(self.path)


# ─────────────────────────────────────────────────────────────────────────────
# The door
# ─────────────────────────────────────────────────────────────────────────────

Handler = Callable[[InboundMessage], str]


class Door:
    """Polls Telegram, enforces the allowlist, and replies to every accepted message."""

    def __init__(
        self,
        transport: Transport,
        allowlist: Allowlist,
        audit: AuditLog,
        handler: Handler,
        *,
        offsets: OffsetStore | None = None,
        interim_after_seconds: int = 10,
        poll_timeout_seconds: int = 30,
        chunk_limit: int = CHUNK_LIMIT,
    ) -> None:
        self._transport = transport
        self._allowlist = allowlist
        self._audit = audit
        self._handler = handler
        self._offsets = offsets
        self._interim_after_seconds = interim_after_seconds
        self._poll_timeout_seconds = poll_timeout_seconds
        self._chunk_limit = chunk_limit

    # ── inbound ──────────────────────────────────────────────────────────

    def handle_update(self, update: Mapping[str, Any]) -> bool:
        """Process one update. Returns whether the handler was invoked.

        The ordering here is the security property: classify, then **allowlist**,
        and only then reach the handler. Nothing above the allowlist check can
        call a model, touch memory, or send a reply.
        """
        message = classify_update(update)
        if message is None:
            return False

        if not self._allowlist.allows(message.user_id):
            # Audited, then silence. An error reply would confirm the bot is live
            # and whose it is; a stranger learns nothing from no answer at all.
            self._audit.record(
                AuditEvent(
                    actor=f"telegram:{message.user_id}",
                    action="door.inbound.refused",
                    outcome="refused",
                    blast="BLACK",
                    reason=(
                        "sender is not on the allowlist; discarded without a reply "
                        "and without any model call"
                    ),
                    detail={
                        "update_id": message.update_id,
                        "chat_id": message.chat_id,
                        "kind": message.kind,
                    },
                )
            )
            return False

        self._audit.record(
            AuditEvent(
                actor=f"telegram:{message.user_id}",
                action="door.inbound.accepted",
                outcome="ok",
                reason=f"owner message accepted ({message.kind}, language={message.language})",
                detail={
                    "update_id": message.update_id,
                    "kind": message.kind,
                    "is_forwarded": message.is_forwarded,
                    "chars": len(message.text),
                },
            )
        )

        # The <3 s acknowledgement (R1.5, N4): a typing indicator, which is what a
        # Telegram user actually reads as "it heard me".
        self._safe_typing(message.chat_id)

        interim = self._schedule_interim(message)
        try:
            reply = self._handler(message)
        except Exception as exc:
            self._audit.record(
                AuditEvent(
                    actor=f"telegram:{message.user_id}",
                    action="door.turn.error",
                    outcome="error",
                    reason=f"handler raised {type(exc).__name__}",
                    detail={"update_id": message.update_id},
                )
            )
            reply = "Something broke on my side handling that. It is written to the audit log."
        finally:
            interim.cancel()

        # R1.4: silence is a defect. Even an empty result gets an answer.
        self.send(message.chat_id, reply or "(no reply produced)")
        return True

    def _schedule_interim(self, message: InboundMessage) -> threading.Timer:
        """Tell the owner what is happening if work outlasts the threshold (R1.5)."""

        def announce() -> None:
            self._safe_send(
                message.chat_id,
                "Still working on that — I will come back with the result.",
            )

        timer = threading.Timer(self._interim_after_seconds, announce)
        timer.daemon = True
        timer.start()
        return timer

    # ── outbound ─────────────────────────────────────────────────────────

    def send(self, chat_id: int, text: str) -> None:
        """Send, chunked. Raises :class:`TransportError` if Telegram refuses."""
        for chunk in chunk_text(text, self._chunk_limit):
            self._transport.call("sendMessage", {"chat_id": chat_id, "text": chunk})

    def _safe_send(self, chat_id: int, text: str) -> None:
        """Best-effort send for cosmetic messages only.

        Used for the interim notice. A failed *cosmetic* message must not abort a
        turn, but note the asymmetry: the real reply uses :meth:`send`, which does
        raise, because a silently dropped answer is indistinguishable from the bot
        being dead.
        """
        with contextlib.suppress(TransportError):
            self.send(chat_id, text)

    def _safe_typing(self, chat_id: int) -> None:
        with contextlib.suppress(TransportError):
            self._transport.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    # ── polling ──────────────────────────────────────────────────────────

    def poll_once(self, offset: int) -> int:
        """Fetch and handle one batch. Returns the next offset.

        The offset advances past every update this batch contained, handled or
        not — including refused ones. Otherwise a single message from a stranger
        would be re-fetched forever, and the audit log would fill with identical
        refusals until the disk did.
        """
        payload = self._transport.call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": self._poll_timeout_seconds,
                "allowed_updates": ["message", "edited_message"],
            },
        )
        updates = payload.get("result", payload)
        if not isinstance(updates, list):
            return offset

        next_offset = offset
        for update in updates:
            if not isinstance(update, Mapping):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                next_offset = max(next_offset, update_id + 1)
            self.handle_update(update)

        if self._offsets is not None and next_offset != offset:
            self._offsets.write(next_offset)
        return next_offset

    @staticmethod
    def _interruptible_wait(seconds: float, should_stop: Callable[[], bool]) -> None:
        """Sleep in short slices so a shutdown signal is noticed promptly.

        A single ``time.sleep(60)`` inside the backoff means a ``SIGTERM`` is not
        seen for up to a minute. Measured on a real container: asked to stop during
        a backoff it took **29 seconds** to exit, and Docker sends ``SIGKILL`` after
        10 — so a redeploy during an outage would kill the process mid-write instead
        of letting it record why it stopped. Found by timing a real run, not by a
        test.
        """
        remaining = seconds
        while remaining > 0 and not should_stop():
            slice_seconds = min(remaining, POLL_TICK_SECONDS)
            time.sleep(slice_seconds)
            remaining -= slice_seconds

    def run(
        self,
        should_stop: Callable[[], bool],
        *,
        wait: Callable[[float, Callable[[], bool]], None] | None = None,
    ) -> None:
        """Poll until ``should_stop()``.

        A transport failure is retried rather than fatal — Telegram being briefly
        unreachable is a normal condition, not an error (R11).

        **But retrying must not be free.** The first version of this loop had no
        backoff and no deduplication, and running the container with a deliberately
        wrong token produced *four identical audit rows inside one second* — it
        would have spun at full speed forever on a 2-vCPU box shared with the
        students' bot, filling the disk with identical rows. Found by running it,
        not by a test.

        So: exponential backoff capped at :data:`MAX_POLL_BACKOFF_SECONDS`, reset
        on any success; a repeated identical failure is **counted, not re-recorded**,
        with one summary row when it finally clears; and a *permanent* failure (a
        wrong token) jumps straight to the cap and is audited ``RED``, because no
        amount of retrying will fix it and the owner has to act.
        """
        pause = wait or self._interruptible_wait
        offset = self._offsets.read() if self._offsets is not None else 0
        backoff = 0.0
        repeats = 0
        last_error = ""

        while not should_stop():
            try:
                offset = self.poll_once(offset)
            except TransportError as exc:
                message = str(exc)
                if message == last_error:
                    # Same failure again: count it, do not write another row.
                    repeats += 1
                else:
                    last_error = message
                    repeats = 0
                    self._audit.record(
                        AuditEvent(
                            actor="system",
                            action="door.poll.error",
                            outcome="error",
                            blast="RED" if exc.is_permanent else "GREEN",
                            reason=(
                                f"TELEGRAM REJECTED THE CREDENTIAL ({exc}) — this will not "
                                "recover on its own; the bot token needs the owner"
                                if exc.is_permanent
                                else f"telegram unreachable: {exc}; backing off"
                            ),
                        )
                    )
                backoff = (
                    MAX_POLL_BACKOFF_SECONDS
                    if exc.is_permanent
                    else min(max(backoff * 2, 1.0), MAX_POLL_BACKOFF_SECONDS)
                )
                pause(backoff, should_stop)
                continue

            if backoff:
                self._audit.record(
                    AuditEvent(
                        actor="system",
                        action="door.poll.recovered",
                        outcome="ok",
                        reason=(
                            f"polling recovered after {repeats + 1} consecutive failure(s) "
                            f"({last_error})"
                        ),
                    )
                )
            backoff = 0.0
            repeats = 0
            last_error = ""
