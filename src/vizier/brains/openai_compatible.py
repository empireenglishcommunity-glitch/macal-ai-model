"""Adapter for providers speaking the OpenAI chat-completions shape.

Covers the provider configured today and most others that could replace it, which
is precisely the point of N6: swapping provider is a config entry, not a refactor.

**No model name appears in this file.** The model arrives from ``config.yaml`` via
the factory. ``tests/test_no_model_names_in_code.py`` enforces that.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from vizier.brains.base import BrainReply, BrainRequest, BrainUnavailableError
from vizier.brains.http import post_json

#: Injected so tests can drive the adapter with no network. Same seam pattern as
#: the door's ``Transport``.
PostJson = Callable[..., Mapping[str, Any]]


class OpenAICompatibleBrain:
    """One model on one OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        post: PostJson | None = None,
    ) -> None:
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._post: PostJson = post or post_json

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def complete(self, request: BrainRequest) -> BrainReply:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = self._post(
            f"{self._base_url}/chat/completions",
            {
                "model": self._model,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
            headers=headers,
            timeout=self._timeout,
        )
        return self._parse(payload)

    def _parse(self, payload: Mapping[str, Any]) -> BrainReply:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            # A 200 with no choices is a provider bug, not an answer. Treating it
            # as an empty string would deliver silence and look like the model
            # having nothing to say.
            raise BrainUnavailableError("response contained no choices")
        first = choices[0]
        if not isinstance(first, Mapping):
            raise BrainUnavailableError("malformed choice in response")

        message = first.get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise BrainUnavailableError("response contained no message content")

        usage = payload.get("usage")
        prompt_tokens = completion_tokens = 0
        if isinstance(usage, Mapping):
            prompt_tokens = _as_int(usage.get("prompt_tokens"))
            completion_tokens = _as_int(usage.get("completion_tokens"))

        return BrainReply(
            text=content,
            provider=self._provider,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            truncated=first.get("finish_reason") == "length",
        )


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
