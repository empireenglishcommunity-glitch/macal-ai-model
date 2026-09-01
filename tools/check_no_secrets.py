#!/usr/bin/env python3.12
"""Fail the build if a secret-shaped string appears in any tracked file.

A committed secret is a **live incident** in this ecosystem: it requires
rotation, because removing it from ``HEAD`` does not remove it from history.
Five secrets have leaked here before, one of them powering a live,
payment-collecting bot nobody remembered existed.

Scans only files git tracks, so local `.env` files and build output are ignored
by construction rather than by an exclusion list that can drift.

Usage:
    python3.12 tools/check_no_secrets.py
Exit codes:
    0 clean · 1 secret found · 2 could not run (treated as failure by CI)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vizier.config import find_secret_shapes

#: Files whose *purpose* is to describe secret shapes. Excluding them by exact
#: path, never by pattern, so a new file cannot quietly inherit an exemption.
ALLOWED: frozenset[str] = frozenset(
    {
        "src/vizier/config.py",  # defines SECRET_SHAPES
        "tests/test_config.py",  # asserts the shapes are detected
        "tools/check_no_secrets.py",  # this file
    }
)

BINARY_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".ico", ".woff", ".woff2"}
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    try:
        files = tracked_files()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"FAIL could not list tracked files: {exc}", file=sys.stderr)
        return 2

    if not files:
        # A scan of nothing passes vacuously; that is a failure, not a pass.
        print("FAIL no tracked files found — refusing to report a vacuous pass", file=sys.stderr)
        return 2

    scanned = 0
    offences: list[str] = []
    for name in files:
        if name in ALLOWED or Path(name).suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = Path(name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            shapes = find_secret_shapes(line)
            if shapes:
                # Report the SHAPE, never the match: this output goes into PR
                # bodies and CI logs, which are more public than the file was.
                offences.append(f"{name}:{lineno}: matches {list(shapes)}")

    if offences:
        print(f"FAIL {len(offences)} secret-shaped string(s) in tracked files:", file=sys.stderr)
        for offence in offences:
            print(f"  {offence}", file=sys.stderr)
        print(
            "\nThis is a LIVE INCIDENT if the value is real: rotate the credential.\n"
            "Removing it from HEAD does not remove it from git history.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK no secret-shaped strings in {scanned} tracked text files "
        f"({len(ALLOWED)} shape-defining files excluded by exact path)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
