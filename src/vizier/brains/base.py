"""The brain seam.

This module is the reason the Vizier is not married to a vendor (design.md D4,
requirement N6). Everything above it — the router, the orchestrator, the door —
knows only :class:`Brain`. Nothing above it knows a model name, a provider name,
or an HTTP shape.

**The exception hierarchy is the load-bearing part**, because it encodes what the
router is allowed to do about each kind of failure:

.. code-block:: text

    BrainError                  something went wrong
    ├── BrainUnavailableError        transient. TRY THE NEXT TIER.
    │   └── RateLimitedError         transient with a hint. TRY THE NEXT TIER.
    ├── BrainAuthError          a credential is wrong. Try the next tier, but
    │                           SAY SO LOUDLY — this will not fix itself, and a
    │                           silent permanent fallback is how a system runs
    │                           for weeks on its weakest brain without anyone
    │                           noticing.
    └── BrainRefusedError            the request itself is bad (e.g. too long). The
                                next tier will refuse it too, so do not waste
                                the attempt.

That last distinction matters. Retrying a malformed request across every provider
turns one clear error into four confusing ones and burns the rate limit that the
fallback chain exists to protect.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class BrainRequest:
    """What to ask. Carries no model and no provider — the tier decides those."""

    messages: Sequence[Message]
    max_tokens: int = 1024
    temperature: float = 0.3

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("a brain request needs at least one message")


@dataclass(frozen=True, slots=True)
class BrainReply:
    """An answer, plus enough provenance to answer "which brain said this?" (R11.1)."""

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: True when the provider signalled it stopped early. The caller may want to
    #: retry with a larger budget rather than silently deliver a truncated answer.
    truncated: bool = False


class BrainError(Exception):
    """Base for every brain failure."""


class BrainUnavailableError(BrainError):
    """Transient. The router should try the next tier."""


class RateLimitedError(BrainUnavailableError):
    """Quota exhausted. Transient, and the whole reason the fallback chain exists.

    On a free tier this is a **normal operating condition**, not an incident
    (R11.3): the binding limit for an agent loop is tokens-per-minute, and hitting
    it must cost a fallback, never a turn.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class BrainAuthError(BrainError):
    """A credential is missing, wrong, or revoked.

    Deliberately **not** a subclass of :class:`BrainUnavailableError`: the router still
    falls through so the owner gets an answer, but this must be audited as a
    distinct, loud condition. A rotated key that quietly demotes every turn to the
    weakest brain is exactly the "quietly off, not visibly broken" failure this
    ecosystem keeps rediscovering.
    """


class BrainRefusedError(BrainError):
    """The request is unacceptable to any provider — too long, malformed, filtered.

    The router must **not** retry this elsewhere.
    """


@runtime_checkable
class Brain(Protocol):
    """One configured model, reachable over one provider.

    Implementations must translate provider-specific failures into the hierarchy
    above. A provider that leaks its own exception type breaks the router's
    ability to reason about failure, which is the entire point of this seam.
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def complete(self, request: BrainRequest) -> BrainReply: ...


@dataclass(frozen=True, slots=True)
class Attempt:
    """One tier tried, and what happened. Assembled into the audit trail."""

    tier: str
    provider: str
    model: str
    outcome: Literal["ok", "unavailable", "rate_limited", "auth", "refused", "skipped"]
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RouterResult:
    """The outcome of a routed request.

    Exactly one of ``reply`` or ``queued`` is meaningful. ``queued`` is not a
    failure: it is the promise in R11.2 that input is never lost, kept.
    """

    reply: BrainReply | None
    answered_by: str | None
    attempts: tuple[Attempt, ...] = field(default_factory=tuple)
    queued: bool = False

    @property
    def ok(self) -> bool:
        return self.reply is not None

    def summary(self) -> str:
        """One line explaining the route taken — the answer to "which brain?"."""
        if self.queued:
            return "queued: every configured brain was unavailable"
        trail = " -> ".join(f"{a.tier}:{a.outcome}" for a in self.attempts)
        return f"answered by {self.answered_by} [{trail}]"
