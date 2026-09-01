"""Tests for the brain seam: the two adapters and the factory.

The point of these tests is that the two adapters speak **genuinely different**
wire formats and produce an identical :class:`BrainReply`. That is what makes N6
("adding a provider is one adapter and one config entry") a fact rather than an
aspiration.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from vizier.brains.base import (
    Brain,
    BrainAuthError,
    BrainRefusedError,
    BrainReply,
    BrainRequest,
    BrainUnavailableError,
    Message,
    RateLimitedError,
)
from vizier.brains.factory import build_brains
from vizier.brains.http import _from_status
from vizier.brains.local_daemon import LocalDaemonBrain
from vizier.brains.openai_compatible import OpenAICompatibleBrain
from vizier.config import ConfigError, load_config

REPO_ROOT = Path(__file__).resolve().parent.parent
ASK = BrainRequest(messages=[Message(role="user", content="salam")])


class RecordingPost:
    """Captures the outgoing call and returns a canned response."""

    def __init__(self, response: Mapping[str, Any] | Exception) -> None:
        self.response = response
        self.url: str | None = None
        self.payload: Mapping[str, Any] | None = None
        self.headers: Mapping[str, str] | None = None

    def __call__(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> Mapping[str, Any]:
        self.url, self.payload, self.headers = url, payload, headers or {}
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


# ─── adapter A: the OpenAI-compatible shape ────────────────────────────────

CHAT_OK: dict[str, Any] = {
    "choices": [
        {"message": {"role": "assistant", "content": "wa alaykum"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 4},
}


def test_openai_compatible_parses_a_reply() -> None:
    post = RecordingPost(CHAT_OK)
    brain = OpenAICompatibleBrain(
        provider="p", base_url="https://x.invalid/v1", model="m", api_key="k", post=post
    )
    reply = brain.complete(ASK)

    assert reply == BrainReply(
        text="wa alaykum", provider="p", model="m", prompt_tokens=11, completion_tokens=4
    )
    assert post.url == "https://x.invalid/v1/chat/completions"
    assert post.payload is not None and post.payload["model"] == "m"


def test_openai_compatible_sends_a_bearer_token_when_it_has_one() -> None:
    post = RecordingPost(CHAT_OK)
    OpenAICompatibleBrain(
        provider="p", base_url="https://x.invalid/v1", model="m", api_key="secret", post=post
    ).complete(ASK)
    assert post.headers == {"Authorization": "Bearer secret"}


def test_openai_compatible_omits_the_header_without_a_key() -> None:
    post = RecordingPost(CHAT_OK)
    OpenAICompatibleBrain(
        provider="p", base_url="https://x.invalid/v1", model="m", post=post
    ).complete(ASK)
    assert post.headers == {}


def test_a_truncated_reply_is_flagged_not_hidden() -> None:
    post = RecordingPost(
        {"choices": [{"message": {"content": "half an ans"}, "finish_reason": "length"}]}
    )
    brain = OpenAICompatibleBrain(
        provider="p", base_url="https://x.invalid/v1", model="m", post=post
    )
    assert brain.complete(ASK).truncated is True


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        {"choices": ["not a mapping"]},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_a_200_with_no_usable_content_is_unavailable_not_empty(response: dict[str, Any]) -> None:
    """Returning "" here would deliver silence and look like the model having
    nothing to say. A provider bug must not masquerade as an answer."""
    brain = OpenAICompatibleBrain(
        provider="p", base_url="https://x.invalid/v1", model="m", post=RecordingPost(response)
    )
    with pytest.raises(BrainUnavailableError):
        brain.complete(ASK)


# ─── adapter B: a genuinely different shape — the proof of N6 ──────────────

DAEMON_OK: dict[str, Any] = {
    "message": {"role": "assistant", "content": "local answer"},
    "prompt_eval_count": 7,
    "eval_count": 3,
    "done_reason": "stop",
}


def test_local_daemon_parses_its_own_wire_format() -> None:
    post = RecordingPost(DAEMON_OK)
    brain = LocalDaemonBrain(
        provider="local", base_url="http://127.0.0.1:11434", model="m", post=post
    )
    reply = brain.complete(ASK)

    assert reply.text == "local answer"
    assert (reply.prompt_tokens, reply.completion_tokens) == (7, 3)
    # Different path, different body, no auth — and the caller cannot tell.
    assert post.url == "http://127.0.0.1:11434/api/chat"
    assert post.payload is not None and post.payload["stream"] is False
    assert post.payload["options"]["num_predict"] == ASK.max_tokens
    assert post.headers == {}


def test_local_daemon_flags_truncation_in_its_own_vocabulary() -> None:
    post = RecordingPost({**DAEMON_OK, "done_reason": "length"})
    brain = LocalDaemonBrain(provider="local", base_url="http://x", model="m", post=post)
    assert brain.complete(ASK).truncated is True


@pytest.mark.parametrize("response", [{}, {"message": "not a mapping"}, {"message": {}}])
def test_local_daemon_rejects_a_response_with_no_content(response: dict[str, Any]) -> None:
    brain = LocalDaemonBrain(
        provider="local", base_url="http://x", model="m", post=RecordingPost(response)
    )
    with pytest.raises(BrainUnavailableError):
        brain.complete(ASK)


def test_both_adapters_satisfy_the_same_protocol() -> None:
    """The seam, asserted directly."""
    cloud: Brain = OpenAICompatibleBrain(provider="p", base_url="https://x", model="m")
    local: Brain = LocalDaemonBrain(provider="local", base_url="http://y", model="n")
    assert isinstance(cloud, Brain)
    assert isinstance(local, Brain)


def test_both_adapters_produce_the_same_reply_shape() -> None:
    """Two different wire formats, one identical reply — the seam, demonstrated.

    The first version of this test compared ``vars()`` on the two replies. Both
    are ``slots=True`` dataclasses, so ``vars()`` raised no error and simply had
    nothing to compare: the assertion was ``set() == set()`` and could never fail.
    It passed while looking thorough. Now it reads the declared fields and asserts
    both objects actually carry values.
    """
    cloud = OpenAICompatibleBrain(
        provider="cloud", base_url="https://x", model="m", post=RecordingPost(CHAT_OK)
    ).complete(ASK)
    local = LocalDaemonBrain(
        provider="local", base_url="http://y", model="n", post=RecordingPost(DAEMON_OK)
    ).complete(ASK)

    field_names = {field.name for field in fields(BrainReply)}
    assert field_names == {
        "text",
        "provider",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "truncated",
    }

    # Every declared field is readable on both, and provenance genuinely differs.
    for name in field_names:
        assert hasattr(cloud, name) and hasattr(local, name), name
    assert (cloud.provider, cloud.model) == ("cloud", "m")
    assert (local.provider, local.model) == ("local", "n")
    assert cloud.text and local.text
    assert (cloud.prompt_tokens, local.prompt_tokens) == (11, 7)


# ─── status translation: one mapping, shared by every adapter ──────────────


def _http_error(status: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", status, "err", headers or {}, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, RateLimitedError),
        (401, BrainAuthError),
        (403, BrainAuthError),
        (400, BrainRefusedError),
        (413, BrainRefusedError),
        (422, BrainRefusedError),
        (500, BrainUnavailableError),
        (503, BrainUnavailableError),
    ],
)
def test_status_codes_map_to_the_router_s_vocabulary(status: int, expected: type) -> None:
    assert isinstance(_from_status(_http_error(status)), expected)


def test_an_auth_error_is_not_classed_as_transient() -> None:
    """It must NOT subclass BrainUnavailableError: a rotated key that quietly demotes
    every turn to the weakest brain is the "quietly off, not visibly broken"
    failure this ecosystem keeps rediscovering."""
    assert not isinstance(_from_status(_http_error(401)), BrainUnavailableError)


def test_retry_after_is_captured_when_offered() -> None:
    error = _from_status(_http_error(429, {"Retry-After": "12"}))
    assert isinstance(error, RateLimitedError)
    assert error.retry_after_seconds == 12.0


def test_an_unparseable_retry_after_is_ignored_not_fatal() -> None:
    error = _from_status(_http_error(429, {"Retry-After": "soon"}))
    assert isinstance(error, RateLimitedError)
    assert error.retry_after_seconds is None


# ─── the factory ───────────────────────────────────────────────────────────


def test_the_shipped_config_builds_its_enabled_tiers() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    env = dict.fromkeys(config.required_env_vars(), "placeholder")
    brains = build_brains(config, env)
    assert set(brains) == set(config.enabled_tiers())
    for name, brain in brains.items():
        assert brain.model == config.brains.tiers[name].model


def test_a_disabled_tier_builds_nothing() -> None:
    """A restored system comes up inert on purpose."""
    config = load_config(REPO_ROOT / "config.yaml")
    env = dict.fromkeys(config.required_env_vars(), "placeholder")
    assert "private" not in build_brains(config, env)


def test_a_missing_key_fails_at_startup_naming_the_variable_not_the_value() -> None:
    """Fail loudly at boot. The alternative is discovering it when the owner asks
    his first real question."""
    config = load_config(REPO_ROOT / "config.yaml")
    with pytest.raises(ConfigError) as info:
        build_brains(config, {})
    message = str(info.value)
    assert "VIZIER_GROQ_API_KEY" in message
    assert "placeholder" not in message


def test_a_whitespace_only_key_counts_as_missing() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    env = dict.fromkeys(config.required_env_vars(), "   ")
    with pytest.raises(ConfigError, match="missing or empty"):
        build_brains(config, env)


def test_an_unknown_provider_kind_is_refused() -> None:
    """The failure names the known kinds, so the fix is obvious from the message."""
    config = load_config(REPO_ROOT / "config.yaml")
    broken = config.brains.providers["groq"].__class__(
        name="groq",
        kind="telepathy",
        base_url="https://x",
        api_key_env=None,
        paid=False,
    )
    config.brains.providers["groq"] = broken  # type: ignore[index]
    with pytest.raises(ConfigError, match="unsupported kind"):
        build_brains(config, dict.fromkeys(config.required_env_vars(), "x"))
