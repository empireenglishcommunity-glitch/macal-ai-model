"""Tests for the single time-handling module.

Several of these are **regression tests for incidents that actually happened** in
this ecosystem. They are written to fail if the specific mistake is reintroduced,
not merely to exercise the happy path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from vizier.clock import (
    days_since,
    elapsed_since,
    hours_since,
    is_stale,
    parse_stamp,
    to_stamp,
    utcnow,
)

NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


# ─── the incidents ─────────────────────────────────────────────────────────


def test_the_mai_incident_cannot_recur() -> None:
    """A 43-day-streak student was told she had not been active.

    Her real row was ``'2026-08-30 22:39:00'`` (UTC, space-separated) and the
    inactivity cutoff was ``'2026-08-30T12:00:00'``. Compared **as strings**, at
    index 10 ``' '`` (32) sorts before ``'T'`` (84), so the row read as older than
    the cutoff and she was judged inactive — on a gap of 13.35 hours.

    This test pins both halves: that the string comparison really is wrong, and
    that comparing instants gets it right.
    """
    stored = "2026-08-30 22:39:00"
    cutoff_text = "2026-08-30T12:00:00"

    # The original defect, reproduced exactly.
    assert stored < cutoff_text, "the string comparison must still be wrong, or this test is stale"

    # The correct answer, as instants.
    stored_at = parse_stamp(stored)
    cutoff_at = parse_stamp(cutoff_text)
    assert stored_at is not None and cutoff_at is not None
    assert stored_at > cutoff_at

    at_the_time = datetime(2026, 8, 31, 12, 0, 4, tzinfo=UTC)
    measured = hours_since(stored, now=at_the_time)
    assert measured is not None
    assert 13.3 < measured < 13.4  # 13.35 hours, not "over a day"


def test_both_separators_are_the_same_instant() -> None:
    """Historic data contains both shapes. The format must not change the answer."""
    assert parse_stamp("2026-08-30 22:39:00") == parse_stamp("2026-08-30T22:39:00")


def test_aware_minus_naive_does_not_raise() -> None:
    """An aware ``now`` minus a naive stamp raised TypeError, which a broad
    ``except`` swallowed — leaving a churn alert unable to fire for six weeks with
    nothing reporting it. A naive input must be handled, not thrown."""
    assert hours_since("2026-08-31T06:00:00", now=NOW) == 6.0


def test_naive_input_is_interpreted_as_utc_not_local() -> None:
    """Guessing "local" for a naive stamp is what produced the whole
    naive-local-minus-UTC family of bugs. Three sites were latent only because a
    container set no TZ, and would have activated on adding ENV TZ."""
    parsed = parse_stamp("2026-08-31T06:00:00")
    assert parsed == datetime(2026, 8, 31, 6, 0, 0, tzinfo=UTC)
    assert parsed is not None and parsed.tzinfo is UTC


def test_days_since_returns_none_never_zero_for_unknown() -> None:
    """ "I don't know when" and "less than a day ago" are different facts.

    A field that answered 0 for both is what silently blocked re-engagement for
    every student who needed it.
    """
    assert days_since(None) is None
    assert days_since("") is None
    assert days_since("not a date") is None
    # 0 is reserved for a real, recent instant
    assert days_since("2026-08-31T06:00:00", now=NOW) == 0


def test_hours_are_fractional_because_day_truncation_generates_bugs() -> None:
    """``.days`` truncation turned a host offset into a whole extra day."""
    measured = hours_since("2026-08-30T22:39:00", now=NOW)
    assert measured is not None
    assert measured == 13.35
    assert days_since("2026-08-30T22:39:00", now=NOW) == 0


# ─── ordinary behaviour ────────────────────────────────────────────────────


def test_utcnow_is_aware_and_utc() -> None:
    moment = utcnow()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == timedelta(0)


def test_to_stamp_round_trips() -> None:
    rendered = to_stamp(NOW)
    assert rendered == "2026-08-31T12:00:00+0000"
    assert parse_stamp(rendered) == NOW


def test_to_stamp_treats_naive_as_utc_matching_the_parser() -> None:
    naive = datetime(2026, 8, 31, 12, 0, 0)
    assert parse_stamp(to_stamp(naive)) == NOW


def test_offset_stamps_are_converted_not_stripped() -> None:
    """A stamp carrying an offset must be honoured, not truncated to its digits."""
    assert parse_stamp("2026-08-31T15:00:00+03:00") == NOW


def test_trailing_z_is_accepted() -> None:
    assert parse_stamp("2026-08-31T12:00:00Z") == NOW


def test_datetime_input_is_normalised() -> None:
    assert parse_stamp(datetime(2026, 8, 31, 12, 0, 0)) == NOW
    assert parse_stamp(NOW) == NOW


def test_elapsed_since_is_none_for_unreadable_input() -> None:
    assert elapsed_since("rubbish") is None
    assert elapsed_since(None) is None


def test_now_is_injectable_so_history_can_be_replayed() -> None:
    """Replaying real history against a fix is how two false-alarm defects here
    were actually proven fixed. A function that reads the clock internally cannot
    be replayed."""
    assert hours_since("2026-08-31T00:00:00", now=NOW) == 12.0
    assert hours_since("2026-08-31T00:00:00", now=NOW + timedelta(hours=1)) == 13.0


# ─── is_stale forces the caller to decide what unknown means ───────────────


def test_is_stale_measures_hours() -> None:
    assert is_stale("2026-08-30T00:00:00", hours=24, now=NOW) is True
    assert is_stale("2026-08-31T00:00:00", hours=24, now=NOW) is False


def test_is_stale_makes_the_unknown_case_explicit() -> None:
    assert is_stale(None, hours=24, now=NOW) is True
    assert is_stale(None, hours=24, now=NOW, unknown_is_stale=False) is False
