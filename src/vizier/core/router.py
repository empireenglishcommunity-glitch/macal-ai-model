"""The router: pick a tier, fall through on failure, never lose the input.

This module turns "the brains are flaky and free" into a property the rest of the
system does not have to think about (requirements R11.1-R11.3).

Three behaviours are worth stating plainly, because each is a decision:

1. **A brain being unavailable is a normal condition, not an error.** The owner's
   PC is off at night, Egypt has power cuts, and a free tier rate-limits by
   design. A system that treats those as exceptions feels broken most of the time.
2. **A bad *request* is not retried elsewhere.** :class:`BrainRefusedError` stops the
   chain immediately: the next provider will refuse the same thing, and retrying
   turns one clear error into four confusing ones while burning the quota the
   fallback exists to protect.
3. **A wrong credential falls through but is audited loudly.** Otherwise a rotated
   key silently demotes every turn to the weakest brain and nothing reports it —
   the "quietly off, not visibly broken" failure this ecosystem keeps meeting.

Every attempt writes an audit row, so "which brain answered, and why that one?"
is answerable from the log alone (R7.9).
"""

from __future__ import annotations

from collections.abc import Mapping

from vizier.brains.base import (
    Attempt,
    Brain,
    BrainAuthError,
    BrainError,
    BrainRefusedError,
    BrainRequest,
    BrainUnavailableError,
    RateLimitedError,
    RouterResult,
)
from vizier.conscience.audit import AuditEvent, AuditLog
from vizier.core.queue import PendingQueue


class UnknownTierError(Exception):
    """A tier was requested that configuration does not declare."""


class Router:
    """Routes a request through a tier's fallback chain."""

    def __init__(
        self,
        brains: Mapping[str, Brain],
        fallback: Mapping[str, tuple[str, ...]],
        audit: AuditLog,
        *,
        queue: PendingQueue | None = None,
    ) -> None:
        self._brains = dict(brains)
        self._fallback = dict(fallback)
        self._audit = audit
        self._queue = queue

    @property
    def available_tiers(self) -> tuple[str, ...]:
        return tuple(self._brains)

    def ask(
        self,
        tier: str,
        request: BrainRequest,
        *,
        queue_payload: Mapping[str, object] | None = None,
    ) -> RouterResult:
        """Try ``tier``, then its fallbacks. Queue if every one is unavailable.

        ``queue_payload`` is what gets stored if the whole chain fails. Passing it
        is how a caller opts into the "input is never lost" guarantee; a caller
        that omits it gets a plain failed result and must handle that itself.
        """
        chain = self._fallback.get(tier)
        if chain is None:
            raise UnknownTierError(f"no fallback chain declared for tier {tier!r}")

        attempts: list[Attempt] = []
        for candidate in chain:
            brain = self._brains.get(candidate)
            if brain is None:
                # Declared in the chain but not enabled in config. Recorded rather
                # than skipped silently: a chain that quietly has one live link is
                # a chain with no redundancy, and the operator should be able to
                # see that from the trail.
                attempts.append(
                    Attempt(
                        tier=candidate,
                        provider="-",
                        model="-",
                        outcome="skipped",
                        detail="tier is not enabled in configuration",
                    )
                )
                continue

            try:
                reply = brain.complete(request)
            except RateLimitedError as exc:
                attempts.append(self._attempt(candidate, brain, "rate_limited", str(exc)))
                self._record(candidate, brain, "error", f"rate limited, falling through: {exc}")
                continue
            except BrainAuthError as exc:
                attempts.append(self._attempt(candidate, brain, "auth", str(exc)))
                # Loud on purpose: this will not fix itself.
                self._record(
                    candidate,
                    brain,
                    "error",
                    f"CREDENTIAL REJECTED for provider {brain.provider!r} — "
                    f"this will not recover on its own and needs the owner: {exc}",
                    blast="RED",
                )
                continue
            except BrainRefusedError as exc:
                # Stop the chain. Every provider will refuse this request.
                attempts.append(self._attempt(candidate, brain, "refused", str(exc)))
                self._record(
                    candidate,
                    brain,
                    "refused",
                    f"request rejected by the provider; not retried elsewhere "
                    f"because the next one would refuse it too: {exc}",
                )
                return RouterResult(reply=None, answered_by=None, attempts=tuple(attempts))
            except BrainUnavailableError as exc:
                attempts.append(self._attempt(candidate, brain, "unavailable", str(exc)))
                self._record(candidate, brain, "error", f"unavailable, falling through: {exc}")
                continue
            except BrainError as exc:
                # An adapter leaked something outside the known hierarchy. Treat as
                # transient so the owner still gets an answer, but say that the
                # adapter is at fault, not the provider.
                attempts.append(self._attempt(candidate, brain, "unavailable", str(exc)))
                self._record(
                    candidate,
                    brain,
                    "error",
                    f"adapter raised an unclassified BrainError ({type(exc).__name__}); "
                    f"treating as transient: {exc}",
                )
                continue

            attempts.append(self._attempt(candidate, brain, "ok"))
            self._record(
                candidate,
                brain,
                "ok",
                f"answered after {len(attempts)} attempt(s) on chain {list(chain)}",
                extra={
                    "prompt_tokens": reply.prompt_tokens,
                    "completion_tokens": reply.completion_tokens,
                    "truncated": reply.truncated,
                },
            )
            return RouterResult(reply=reply, answered_by=candidate, attempts=tuple(attempts))

        # Every link failed. This is the promise in R11.2.
        queued = False
        if self._queue is not None and queue_payload is not None:
            self._queue.push(
                queue_payload,
                reason=f"every brain in chain {list(chain)} was unavailable",
            )
            queued = True

        self._audit.record(
            AuditEvent(
                actor="system",
                action="brain.exhausted",
                outcome="queued" if queued else "error",
                blast="YELLOW",
                reason=(
                    f"no brain in chain {list(chain)} could answer; "
                    + ("input queued for retry on recovery" if queued else "input NOT queued")
                ),
                detail={
                    "tier": tier,
                    "attempts": [
                        {"tier": a.tier, "outcome": a.outcome, "detail": a.detail} for a in attempts
                    ],
                },
            )
        )
        return RouterResult(reply=None, answered_by=None, attempts=tuple(attempts), queued=queued)

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _attempt(tier: str, brain: Brain, outcome: str, detail: str = "") -> Attempt:
        return Attempt(
            tier=tier,
            provider=brain.provider,
            model=brain.model,
            outcome=outcome,  # type: ignore[arg-type]
            detail=detail,
        )

    def _record(
        self,
        tier: str,
        brain: Brain,
        outcome: str,
        reason: str,
        *,
        blast: str = "GREEN",
        extra: Mapping[str, object] | None = None,
    ) -> None:
        detail: dict[str, object] = {
            "tier": tier,
            "provider": brain.provider,
            "model": brain.model,
        }
        if extra:
            detail.update(extra)
        self._audit.record(
            AuditEvent(
                actor="system",
                action="brain.call",
                outcome=outcome,  # type: ignore[arg-type]
                blast=blast,  # type: ignore[arg-type]
                reason=reason,
                detail=detail,
            )
        )
