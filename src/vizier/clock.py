"""The one place time is handled.

There is **one** "now", **one** parser, and **one** way to express an elapsed
period. Every other module imports from here.

This module is deliberately small and deliberately central, because the single
most expensive defect class in this ecosystem has been time handling. The record,
worth reading before changing anything below:

* A student with a **43-day streak and 100% weekly completion** was told she had
  not been active. ``last_active_at`` was written in two formats — SQL
  ``datetime('now')`` produced ``"2026-08-30 23:59:00"`` (UTC, **space**) while a
  web client wrote ``.isoformat()`` producing ``"...T23:59:00"`` (**local**, "T")
  — and the two were compared **as strings**. At index 10, ``' '`` (32) sorts
  before ``'T'`` (84), so *active 13 hours ago* evaluated as *inactive over a
  day*. See :func:`test_the_mai_incident_cannot_recur`.
* The same naive-local-minus-UTC subtraction existed in **four** places. Three
  were latent rather than misbehaving: the container set no ``TZ``, so naive-local
  happened to equal naive-UTC. They would have activated the moment someone
  "fixed the timezone" by adding ``ENV TZ`` — which is a plausible thing to do.
* A churn alert was **unable to fire for six weeks and nothing reported it**:
  an aware ``now`` minus a naive parsed stamp raises ``TypeError``, which was
  swallowed by a broad ``except ... : continue``, so the result was always empty.
  Silence looked identical to "nothing to report".
* ``.days`` truncation turned a host offset into a whole extra day.

The rules that follow from that history:

1. **Everything is timezone-aware UTC.** A naive input is *interpreted* as UTC —
   never as local time — and that interpretation is explicit, not incidental.
2. **Compare instants, never strings.** Both separators (``" "`` and ``"T"``)
   parse to the same instant, so the format a value was written in cannot change
   the answer.
3. **One canonical output format**, so nothing new gets written in a second shape.
4. **:func:`days_since` returns ``None``, never ``0``, for unknown input.**
   "I don't know when" and "less than a day ago" are different facts, and
   conflating them is how a stale value silently disabled a whole feature.
5. **Elapsed time is available as a float** (:func:`hours_since`). Any decision
   about recency uses hours; ``.days`` truncation is not a rounding detail, it is
   a bug generator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

#: The canonical written form: ISO-8601, "T" separator, explicit ``+00:00``.
#: Anything this module writes uses this and only this.
STAMP_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S%z"


def utcnow() -> datetime:
    """The current instant, timezone-aware, in UTC.

    Never use ``datetime.now()`` or ``datetime.utcnow()`` elsewhere: the first is
    local and the second is *naive*, and subtracting a naive value from an aware
    one raises ``TypeError`` — which is how an alert became unable to fire for six
    weeks without anyone noticing.
    """
    return datetime.now(UTC)


def to_stamp(moment: datetime) -> str:
    """Render an instant in the canonical form.

    A naive input is interpreted as UTC, matching :func:`parse_stamp`, so a
    round-trip is lossless in both directions.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(STAMP_FORMAT)


def parse_stamp(raw: str | datetime | None) -> datetime | None:
    """Parse a stamp into an aware UTC instant, or ``None`` if it cannot be read.

    Accepts both separators on purpose — ``"2026-08-30 22:39:00"`` and
    ``"2026-08-30T22:39:00"`` are the *same instant* here. Historic data in this
    ecosystem contains both, and any function whose answer depends on which one it
    got is a function that will eventually be wrong about a real person.

    Returns ``None`` rather than raising: callers must handle "unknown" as a
    distinct case, and a raise inside a loop over people has already been
    swallowed by a broad ``except`` once.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=UTC) if raw.tzinfo is None else raw.astimezone(UTC)

    text = raw.strip()
    if not text:
        return None
    # Normalise the two things real data does differently: the separator, and a
    # trailing "Z" that fromisoformat did not accept before 3.11.
    text = text.replace(" ", "T", 1) if " " in text[:11] else text
    if text.endswith(("z", "Z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A stamp with no offset is UTC. This is a decision, not an accident: every
    # writer in this system is UTC, and guessing "local" is what produced the
    # naive-local-minus-UTC family of bugs.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def elapsed_since(raw: str | datetime | None, *, now: datetime | None = None) -> timedelta | None:
    """Time elapsed since ``raw``, or ``None`` if it cannot be read.

    ``now`` is injected rather than read from the clock so that every caller can
    be tested at a fixed moment. Functions that read the clock internally cannot
    be replayed, and replaying real history against a fix is how two false-alarm
    defects here were actually proven fixed.
    """
    moment = parse_stamp(raw)
    if moment is None:
        return None
    return (now or utcnow()) - moment


def hours_since(raw: str | datetime | None, *, now: datetime | None = None) -> float | None:
    """Whole and fractional hours since ``raw``, or ``None`` if unknown.

    **Prefer this over :func:`days_since` for any recency decision.** "13.35 hours
    ago" is the fact that mattered in the incident this module exists to prevent;
    a day count cannot express it.
    """
    delta = elapsed_since(raw, now=now)
    return None if delta is None else delta.total_seconds() / 3600.0


def days_since(raw: str | datetime | None, *, now: datetime | None = None) -> int | None:
    """Whole days since ``raw``, or ``None`` if unknown.

    **Returns ``None``, never ``0``, when the input cannot be read.** ``0`` means
    "less than a day ago", which is a completely different claim from "no idea".
    A field that answered ``0`` for both is what silently disabled re-engagement
    for exactly the people it existed to reach.
    """
    delta = elapsed_since(raw, now=now)
    if delta is None:
        return None
    return int(delta.total_seconds() // 86400)


def is_stale(
    raw: str | datetime | None,
    *,
    hours: float,
    now: datetime | None = None,
    unknown_is_stale: bool = True,
) -> bool:
    """Whether ``raw`` is older than ``hours``.

    ``unknown_is_stale`` forces the caller to state what an unreadable value
    means, because the two answers are both defensible and the wrong default is
    invisible: treating unknown as *fresh* hides a broken writer, while treating
    it as *stale* can nag someone with no history. Defaults to fresh-is-unsafe.
    """
    measured = hours_since(raw, now=now)
    if measured is None:
        return unknown_is_stale
    return measured > hours
