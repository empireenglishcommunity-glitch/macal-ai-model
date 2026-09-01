"""Guard: no model or vendor name may appear in ``src/``.

The model is the most replaceable part of this system (design.md D4). If a model
name leaks into code, swapping providers stops being a config change and becomes
a refactor — which is exactly how a system ends up permanently married to one
vendor.

``config.yaml`` is the *only* legitimate home for a model identifier, so this
guard scans ``src/`` alone.

This is deliberately a **test**, not a shell grep in a runbook, because a runbook
is a suggestion and a failing test is a wall. And it verifies itself in both
directions: :func:`test_guard_detects_a_planted_name` proves the guard can
actually fail, because a check that cannot fail is worse than no check.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

#: Word-boundary matched so ordinary English survives: ``corpus`` must not trip
#: ``opus``, and ``llama`` must not trip on a substring of something else.
FORBIDDEN = (
    "gpt",
    "claude",
    "sonnet",
    "opus",
    "haiku",
    "llama",
    "qwen",
    "gemini",
    "gemma",
    "kimi",
    "deepseek",
    "mistral",
    "mixtral",
    "grok",
)

#: The trailing boundary is a negative lookahead for a LETTER, not ``\b``.
#:
#: This is the whole subtlety, and the first version of this guard got it wrong:
#: ``\bqwen\b`` does **not** match ``qwen3:8b``, because ``\b`` requires a
#: non-word character after ``qwen`` and ``3`` is a word character. The guard
#: would have passed a real model name straight through while looking correct.
#: Caught by :func:`test_guard_detects_a_planted_name`, which is why that test
#: exists.
#:
#: ``(?![A-Za-z])`` admits digits, hyphens, colons and dots — so ``qwen3``,
#: ``gpt-4`` and ``llama3.1`` are caught — while still refusing to fire on
#: ordinary English like ``grokking`` or ``corpus``.
PATTERN = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")(?![A-Za-z])", re.IGNORECASE)


def _python_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_src_contains_no_model_or_vendor_names() -> None:
    offences: list[str] = []
    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = PATTERN.search(line)
            if match:
                offences.append(f"{path.relative_to(SRC.parent.parent)}:{lineno}: {match.group(1)}")

    assert not offences, (
        "Model or vendor names must live in config.yaml, never in code (design.md D4, N6):\n"
        + "\n".join(offences)
    )


def test_guard_detects_a_planted_name() -> None:
    """The guard must be able to fail. Verified in both directions.

    The version-suffixed cases are the ones that matter: real model identifiers
    almost always carry a digit, and the first version of this guard silently
    missed every one of them.
    """
    assert PATTERN.search('model = "some-model-8b"') is None

    for planted in (
        'model = "qwen3:8b"',  # digit immediately after the name
        'model = "gpt-4"',
        'model = "llama3.1:70b"',
        'model = "gemma2"',
        'model = "deepseek-v4-pro"',
        'model = "claude-opus"',
        "# ask GPT about it",
        "MISTRAL_URL = ...",
    ):
        assert PATTERN.search(planted) is not None, planted


def test_guard_does_not_trip_on_ordinary_english() -> None:
    """Boundaries matter in both directions.

    ``corpus`` contains ``opus`` and ``grokking`` contains ``grok``; neither is a
    model reference, and a guard that fires on them is a guard people learn to
    ignore — the same failure as a check that is red on a healthy system.
    """
    for benign in (
        "a corpus of text",
        "the opustest suite",
        "grokking the problem",
        "geminid meteor shower",
        "llamas are mammals",  # trailing letter, not a version
    ):
        assert PATTERN.search(benign) is None, benign


def test_there_is_something_to_scan() -> None:
    """A guard that scans zero files passes vacuously.

    This ecosystem shipped a check that printed "145/145 conforming" while
    silently skipping corrupted input. Assert the scan had material.
    """
    assert len(_python_files()) >= 5
