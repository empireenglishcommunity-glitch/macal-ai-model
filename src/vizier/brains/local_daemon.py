"""Adapter for the local model daemon — tier D, the private/offline brain.

**This adapter exists in task 1.3 rather than Phase 7 on purpose: it is the proof
of N6.** A second adapter that merely repeated the OpenAI shape would prove
nothing about the seam. This one speaks a genuinely different wire format —
a different path, a different request body, a different response shape, and no
authentication at all — and the router cannot tell the difference.

Its real job comes later (requirement R12.4): sensitive ministries route here and
nowhere else, so nothing about the owner's money, health or family leaves his own
hardware. Ships **disabled**.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vizier.brains.base import BrainReply, BrainRequest, BrainUnavailableError
from vizier.brains.http import post_json
from vizier.brains.openai_compatible import PostJson


class LocalDaemonBrain:
    """One local model, reached over the daemon's own HTTP API."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        post: PostJson | None = None,
    ) -> None:
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._model = model
        # Longer default than a hosted provider: a model on consumer hardware is
        # slower, and a timeout here would send the turn to a *cloud* brain, which
        # for a sensitive ministry is the one outcome that must never happen.
        self._timeout = timeout
        self._post: PostJson = post or post_json

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def complete(self, request: BrainRequest) -> BrainReply:
        payload = self._post(
            f"{self._base_url}/api/chat",
            {
                "model": self._model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                },
            },
            # No Authorization header at all: it is on the loopback interface, and
            # localhost binding IS the firewall on this infrastructure.
            headers={},
            timeout=self._timeout,
        )
        return self._parse(payload)

    def _parse(self, payload: Mapping[str, Any]) -> BrainReply:
        message = payload.get("message")
        if not isinstance(message, Mapping):
            raise BrainUnavailableError("response contained no message")
        content = message.get("content")
        if not isinstance(content, str):
            raise BrainUnavailableError("response contained no message content")

        return BrainReply(
            text=content,
            provider=self._provider,
            model=self._model,
            prompt_tokens=_as_int(payload.get("prompt_eval_count")),
            completion_tokens=_as_int(payload.get("eval_count")),
            # The daemon reports why it stopped in its own vocabulary.
            truncated=payload.get("done_reason") == "length",
        )


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
