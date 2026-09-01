"""Tests for the minimal turn handler and for startup refusal.

Two themes: the handler must never claim a capability it does not have, and the
process must refuse to start in a state that *looks* healthy but is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vizier.brains.base import BrainReply, BrainRequest, BrainUnavailableError
from vizier.config import ConfigError, load_config
from vizier.conscience.audit import AuditLog
from vizier.core.conversation import Conversation
from vizier.core.queue import PendingQueue
from vizier.core.router import Router
from vizier.door.telegram import InboundMessage
from vizier.main import build

REPO_ROOT = Path(__file__).resolve().parent.parent
OWNER = 111222333


class FakeBrain:
    def __init__(self, name: str, *, fails: Exception | None = None, text: str = "answer") -> None:
        self._name = name
        self._fails = fails
        self._text = text

    @property
    def provider(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return f"model-{self._name}"

    def complete(self, request: BrainRequest) -> BrainReply:
        if self._fails is not None:
            raise self._fails
        return BrainReply(text=self._text, provider=self.provider, model=self.model)


def msg(text: str, *, kind: str = "text", language: str = "en") -> InboundMessage:
    return InboundMessage(
        update_id=1,
        chat_id=OWNER,
        user_id=OWNER,
        message_id=1,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        language=language,
    )


def build_conversation(
    tmp_path: Path, brains: dict[str, FakeBrain]
) -> tuple[Conversation, AuditLog, PendingQueue]:
    audit = AuditLog(tmp_path / "audit.jsonl")
    queue = PendingQueue(tmp_path / "queue.jsonl")
    chain = {"thinking": ("thinking", "reflex"), "reflex": ("reflex",)}
    router = Router(brains, chain, audit, queue=queue)
    return Conversation(router, audit, queue), audit, queue


# ─── ordinary turns ────────────────────────────────────────────────────────


def test_a_question_gets_the_brain_s_answer(tmp_path: Path) -> None:
    conversation, _, _ = build_conversation(tmp_path, {"thinking": FakeBrain("t", text="hello")})
    assert conversation(msg("hi")) == "hello"


def test_the_system_prompt_and_the_user_message_are_both_sent(tmp_path: Path) -> None:
    seen: list[BrainRequest] = []

    class Capturing(FakeBrain):
        def complete(self, request: BrainRequest) -> BrainReply:
            seen.append(request)
            return super().complete(request)

    conversation, _, _ = build_conversation(tmp_path, {"thinking": Capturing("t")})
    conversation(msg("what is my server ip"))

    assert len(seen) == 1
    roles = [message.role for message in seen[0].messages]
    assert roles == ["system", "user"]
    assert seen[0].messages[1].content == "what is my server ip"


def test_a_fallback_is_disclosed_but_a_normal_answer_is_not_annotated(tmp_path: Path) -> None:
    """Reporting the route every time is noise that trains him to stop reading.
    Reporting it only on a fallback makes a degraded system visible."""
    healthy, _, _ = build_conversation(tmp_path / "a", {"thinking": FakeBrain("t", text="fine")})
    assert healthy(msg("hi")) == "fine"

    degraded, _, _ = build_conversation(
        tmp_path / "b",
        {
            "thinking": FakeBrain("t", fails=BrainUnavailableError("down")),
            "reflex": FakeBrain("r", text="fine"),
        },
    )
    answer = degraded(msg("hi"))
    assert "answered by the reflex brain" in answer
    assert "thinking was unavailable" in answer


def test_a_truncated_answer_says_so(tmp_path: Path) -> None:
    class Truncating(FakeBrain):
        def complete(self, request: BrainRequest) -> BrainReply:
            return BrainReply(text="half", provider="t", model="m", truncated=True)

    conversation, _, _ = build_conversation(tmp_path, {"thinking": Truncating("t")})
    assert "cut off at the token limit" in conversation(msg("write me an essay"))


# ─── honesty about what it cannot do (R10.2) ───────────────────────────────


def test_when_every_brain_is_down_it_says_the_message_is_saved(tmp_path: Path) -> None:
    """He must not wonder whether to resend."""
    conversation, _, queue = build_conversation(
        tmp_path,
        {
            "thinking": FakeBrain("t", fails=BrainUnavailableError("down")),
            "reflex": FakeBrain("r", fails=BrainUnavailableError("down")),
        },
    )
    answer = conversation(msg("remember this"))
    assert "saved" in answer
    assert "do not need to resend" in answer
    assert queue.depth() == 1


def test_the_queued_notice_is_arabic_for_an_arabic_message(tmp_path: Path) -> None:
    conversation, _, _ = build_conversation(
        tmp_path, {"thinking": FakeBrain("t", fails=BrainUnavailableError("down"))}
    )
    answer = conversation(msg("افتكر ده", language="ar"))
    assert "محفوظة" in answer


@pytest.mark.parametrize("kind", ["voice", "photo", "document", "audio", "video_note"])
def test_unsupported_media_is_refused_honestly_not_dropped(tmp_path: Path, kind: str) -> None:
    conversation, _, _ = build_conversation(tmp_path, {"thinking": FakeBrain("t")})
    answer = conversation(msg("", kind=kind))
    assert "cannot handle" in answer
    assert kind in answer


def test_help_is_offered_in_the_owner_s_language(tmp_path: Path) -> None:
    conversation, _, _ = build_conversation(tmp_path, {"thinking": FakeBrain("t")})
    assert "/status" in conversation(msg("/help"))
    assert "الوزير" in conversation(msg("/help", language="ar"))


def test_help_lists_what_is_not_built_yet(tmp_path: Path) -> None:
    """An assistant that quietly forgets looks broken rather than unfinished."""
    conversation, _, _ = build_conversation(tmp_path, {"thinking": FakeBrain("t")})
    answer = conversation(msg("/help"))
    assert "Not built yet" in answer
    assert "memory" in answer


def test_the_system_prompt_admits_it_has_no_memory(tmp_path: Path) -> None:
    seen: list[BrainRequest] = []

    class Capturing(FakeBrain):
        def complete(self, request: BrainRequest) -> BrainReply:
            seen.append(request)
            return super().complete(request)

    conversation, _, _ = build_conversation(tmp_path, {"thinking": Capturing("t")})
    conversation(msg("hi"))
    assert "NO memory" in seen[0].messages[0].content


# ─── /status derives, never remembers (R10.1) ──────────────────────────────


def test_status_reports_real_numbers_from_the_real_sources(tmp_path: Path) -> None:
    conversation, audit, queue = build_conversation(
        tmp_path, {"thinking": FakeBrain("t"), "reflex": FakeBrain("r")}
    )
    queue.push({"text": "pending"}, reason="test")
    conversation(msg("hi"))  # generates audit rows

    status = conversation(msg("/status"))

    assert "thinking" in status and "reflex" in status
    assert "pending queue:  1 item(s)" in status
    assert f"audit rows:     {len(audit.read_all())}" in status
    assert "NOT wired yet" in status


def test_status_lists_what_is_missing_not_only_what_works(tmp_path: Path) -> None:
    conversation, _, _ = build_conversation(tmp_path, {"thinking": FakeBrain("t")})
    status = conversation(msg("/status"))
    for absent in ("memory", "orchestrator", "voice"):
        assert absent in status


# ─── startup refuses states that merely LOOK healthy ───────────────────────


def _env(**overrides: str) -> dict[str, str]:
    config = load_config(REPO_ROOT / "config.yaml")
    env = dict.fromkeys(config.required_env_vars(), "placeholder")
    env.update(overrides)
    return env


def test_an_unset_owner_id_is_reported_as_a_missing_variable() -> None:
    """Two different broken states, two different messages, both refusals.

    An *unset* variable is caught by the missing-variable check first, and that is
    the better message: it names the variable and shows how to verify it without
    printing it. Written after the first version of this test asserted the wrong
    one of the two.
    """
    config = load_config(REPO_ROOT / "config.yaml")
    with pytest.raises(ConfigError, match="missing required environment variable"):
        build(config, _env(VIZIER_TELEGRAM_OWNER_ID=""))


def test_a_present_but_unusable_owner_id_refuses_with_an_empty_allowlist() -> None:
    """The variable is set, so nothing looks missing — and the allowlist is still
    empty. This is the state that would otherwise *look* healthy: the process runs,
    the bot is online, and it obeys nobody. A typo in the ID lands here."""
    config = load_config(REPO_ROOT / "config.yaml")
    with pytest.raises(ConfigError, match="EMPTY allowlist"):
        build(config, _env(VIZIER_TELEGRAM_OWNER_ID="not-a-number"))


def test_startup_names_missing_variables_and_never_their_values() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    with pytest.raises(ConfigError) as info:
        build(config, {})
    message = str(info.value)
    assert "VIZIER_TELEGRAM_TOKEN" in message
    assert "grep -c" in message, "the error should tell him how to check without printing it"
    assert "placeholder" not in message


def test_startup_succeeds_with_a_complete_environment(tmp_path: Path) -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    door, audit = build(config, _env(VIZIER_TELEGRAM_OWNER_ID=str(OWNER)))
    assert door is not None
    assert audit.path == config.paths.audit_log
