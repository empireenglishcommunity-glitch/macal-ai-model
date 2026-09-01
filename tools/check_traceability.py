#!/usr/bin/env python3.12
"""Fail the build if a requirement has no task, or a task cites no requirement.

``tasks.md`` declares this a CI gate rather than a courtesy: *"a requirement with
no task is a requirement that will not happen."*

It also guards the reverse direction, because this ecosystem has been burned by
documents that drifted from reality in **both** directions — spec checkboxes have
read "0/28, in progress" for work live in production for a week, and "45/45" for
work never deployed.

Usage:
    python3.12 tools/check_traceability.py
Exit codes:
    0 traceable · 1 gap found · 2 could not run (treated as failure by CI)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / ".kiro" / "specs" / "vizier-core"
REQUIREMENTS = SPEC / "requirements.md"
TASKS = SPEC / "tasks.md"

#: `### R7 — ...` or `**R7.1**` — the declaration sites in requirements.md
DECLARED = re.compile(r"^#{2,4}\s+(R\d+)\s+—", re.MULTILINE)
#: Non-functional and success criteria are declared in tables, not headings
DECLARED_TABLE = re.compile(r"^\|\s*\*\*(N\d+|S\d+)\*\*\s*\|", re.MULTILINE)
#: Any reference in tasks.md, e.g. `*R:* R7, R7.4` or a traceability table row
REFERENCED = re.compile(r"\b([RNS]\d+)(?:\.\d+)?\b")


def main() -> int:
    for path in (REQUIREMENTS, TASKS):
        if not path.is_file():
            print(f"FAIL missing {path}", file=sys.stderr)
            return 2

    req_text = REQUIREMENTS.read_text(encoding="utf-8")
    task_text = TASKS.read_text(encoding="utf-8")

    declared = set(DECLARED.findall(req_text)) | set(DECLARED_TABLE.findall(req_text))
    if not declared:
        print("FAIL parsed zero requirements — the parser is broken, not the spec", file=sys.stderr)
        return 2

    referenced = {match for match in REFERENCED.findall(task_text)}

    untraced = sorted(declared - referenced, key=lambda s: (s[0], int(s[1:])))
    unknown = sorted(referenced - declared, key=lambda s: (s[0], int(s[1:])))

    if untraced:
        print(
            f"FAIL {len(untraced)} requirement(s) declared in requirements.md with no task "
            f"in tasks.md: {untraced}",
            file=sys.stderr,
        )
    if unknown:
        print(
            f"FAIL {len(unknown)} identifier(s) cited in tasks.md that requirements.md does "
            f"not declare: {unknown}",
            file=sys.stderr,
        )
    if untraced or unknown:
        return 1

    print(
        f"OK {len(declared)} requirements declared, all traced to at least one task; "
        "no task cites an undeclared requirement"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
