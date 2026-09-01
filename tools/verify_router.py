#!/usr/bin/env python3.12
"""Demonstrate the fallback chain against the REAL configuration.

Task 1.3's verification asks for audit rows showing tier fallthrough, and for
proof that input survives every brain being unavailable. Unit tests assert that
with fake brains; this script asserts it with the **shipped `config.yaml`**, the
**real adapters**, and the **real audit log**, so the thing being demonstrated is
the thing that will run.

It makes no network calls: the transport is replaced with one that fails on
command. That is the point — simulating "everything is down" by actually breaking
the network is unreproducible, and `iptables` on the production box to prove a
unit-level property would be reckless.

Usage:
    python3.12 tools/verify_router.py
Exit codes:
    0 every scenario behaved as designed · 1 a scenario did not · 2 could not run
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vizier.brains.base import BrainRequest, BrainUnavailableError, Message
from vizier.brains.factory import build_brains
from vizier.config import load_config
from vizier.conscience.audit import AuditLog
from vizier.core.queue import PendingQueue
from vizier.core.router import Router

REPO_ROOT = Path(__file__).resolve().parent.parent
ASK = BrainRequest(messages=[Message(role="user", content="are you there?")])


class ControllablePost:
    """Stands in for the HTTP layer. Fails for every provider except ``healthy``."""

    def __init__(self, healthy_models: set[str]) -> None:
        self.healthy_models = healthy_models
        self.attempted: list[str] = []

    def __call__(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> Mapping[str, Any]:
        model = str(payload.get("model", "?"))
        self.attempted.append(model)
        if model not in self.healthy_models:
            raise BrainUnavailableError("simulated outage")
        return {
            "choices": [{"message": {"content": "still here"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        }


def _wire(
    healthy: set[str], workdir: Path
) -> tuple[Router, AuditLog, PendingQueue, ControllablePost]:
    config = load_config(REPO_ROOT / "config.yaml")
    env = dict.fromkeys(config.required_env_vars(), "placeholder-not-a-real-key")
    brains = build_brains(config, env)

    post = ControllablePost(healthy)
    for brain in brains.values():
        # Replace only the transport. Every other code path is the shipped one.
        brain._post = post  # type: ignore[attr-defined]

    audit = AuditLog(workdir / "audit.jsonl")
    queue = PendingQueue(workdir / "queue.jsonl")
    return Router(brains, config.brains.fallback, audit, queue=queue), audit, queue, post


def _show(title: str, audit: AuditLog) -> None:
    print(f"\n--- audit rows: {title} " + "-" * max(0, 40 - len(title)))
    for row in audit.read_all():
        print(
            json.dumps(
                {
                    "action": row.get("action"),
                    "outcome": row.get("outcome"),
                    "blast": row.get("blast"),
                    "tier": (row.get("detail") or {}).get("tier"),
                    "reason": row.get("reason"),
                },
                ensure_ascii=False,
            )
        )


def main() -> int:
    config = load_config(REPO_ROOT / "config.yaml")
    tiers = config.enabled_tiers()
    print(f"shipped config: enabled tiers = {list(tiers)}")
    print(f"chain for 'deep' = {list(config.fallback_chain('deep'))}")
    print(f"chain for 'private' = {list(config.fallback_chain('private'))}  <- no cloud fallback")

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as raw_dir:
        workdir = Path(raw_dir)

        # ── Scenario 1: the preferred tier is down, the next one answers ──
        thinking_model = config.brains.tiers["thinking"].model
        assert thinking_model is not None
        router, audit, queue, post = _wire({thinking_model}, workdir / "one")
        result = router.ask("deep", ASK, queue_payload={"text": "are you there?"})

        print("\n[1] preferred tier down, fallback healthy")
        print(f"    attempted models: {post.attempted}")
        print(f"    result: {result.summary()}")
        if not (result.ok and result.answered_by == "thinking"):
            failures.append("scenario 1: expected 'thinking' to answer after 'deep' failed")
        if queue.depth() != 0:
            failures.append("scenario 1: nothing should be queued when a fallback answered")
        _show("scenario 1", audit)

        # ── Scenario 2: everything is down — input must survive ───────────
        router, audit, queue, post = _wire(set(), workdir / "two")
        result = router.ask("deep", ASK, queue_payload={"chat_id": 1, "text": "remember this"})

        print("\n[2] every brain down")
        print(f"    attempted models: {post.attempted}")
        print(f"    result: {result.summary()}")
        print(f"    queue depth: {queue.depth()}")
        if result.ok:
            failures.append("scenario 2: nothing should have answered")
        if not result.queued or queue.depth() != 1:
            failures.append("scenario 2: input was NOT queued — R11.2 violated")
        else:
            stored = queue.peek()[0]
            print(f"    queued payload: {stored['payload']}")
            print(f"    queued reason:  {stored['reason']}")
        _show("scenario 2", audit)

        # ── Scenario 3: recovery — the queued item is still there ─────────
        print("\n[3] recovery")
        drained = PendingQueue(workdir / "two" / "queue.jsonl").drain()
        print(
            f"    drained {len(drained)} item(s); queue depth now "
            f"{PendingQueue(workdir / 'two' / 'queue.jsonl').depth()}"
        )
        if len(drained) != 1:
            failures.append("scenario 3: the queued input did not survive to recovery")

    print()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("OK all three scenarios behaved as designed (fallthrough, queue, recovery)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
