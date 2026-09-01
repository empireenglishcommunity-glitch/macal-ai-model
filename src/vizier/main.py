"""Entrypoint. Wires the pieces together and runs the door.

Startup is deliberately loud and ordered so that a misconfiguration is a clear
message at boot rather than a mystery on the owner's first real question:

1. load and validate ``config.yaml``
2. report which environment variables are **missing by name** (never by value)
3. build the brains for the enabled tiers only
4. print a redacted summary of what is actually wired
5. only then start polling

It refuses to start with an empty allowlist. That is the fail-closed direction:
a bot that runs while obeying nobody looks healthy and is useless, and a bot that
runs while obeying *everybody* would be a disaster. Refusing is the only honest
third option.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
from pathlib import Path
from types import FrameType

from vizier.brains.factory import build_brains
from vizier.config import Config, ConfigError, load_config, missing_env_vars
from vizier.conscience.audit import AuditEvent, AuditLog
from vizier.core.conversation import Conversation
from vizier.core.queue import PendingQueue
from vizier.core.router import Router
from vizier.door.telegram import Allowlist, Door, HttpTransport, OffsetStore

LOG = logging.getLogger("vizier")

_STOP = False


def _request_stop(signum: int, _frame: FrameType | None) -> None:
    """Ask the poll loop to finish the current iteration and exit."""
    global _STOP
    _STOP = True
    LOG.info("received signal %s; stopping after the current poll", signum)


def _configure_logging(config: Config) -> None:
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def build(config: Config, env: dict[str, str]) -> tuple[Door, AuditLog]:
    """Assemble everything. Raises :class:`ConfigError` with an actionable message."""
    missing = missing_env_vars(config, env)
    if missing:
        raise ConfigError(
            "missing required environment variable(s): "
            + ", ".join(missing)
            + f"\nThey belong in the env file on the server, not in this repository. "
            f"Verify one without printing it:  grep -c '^{missing[0]}=.' /opt/macal-vizier/.env"
        )

    allowlist = Allowlist.parse(env.get(config.telegram.owner_ids_env))
    if not allowlist:
        raise ConfigError(
            f"{config.telegram.owner_ids_env} produced an EMPTY allowlist. Refusing to "
            "start: a Vizier that obeys nobody looks healthy and is useless, and one "
            "that obeys everybody would be a disaster. Set it to your numeric Telegram "
            "user ID (from @userinfobot)."
        )

    audit = AuditLog(config.paths.audit_log)
    queue = PendingQueue(config.paths.database.parent / "queue.jsonl")
    brains = build_brains(config, env)
    router = Router(brains, config.brains.fallback, audit, queue=queue)

    door = Door(
        HttpTransport(env[config.telegram.token_env]),
        allowlist,
        audit,
        Conversation(router, audit, queue),
        offsets=OffsetStore(config.paths.database.parent / "offset"),
        interim_after_seconds=config.telegram.interim_after_seconds,
        poll_timeout_seconds=config.telegram.poll_timeout_seconds,
    )
    return door, audit


def main() -> int:
    config_path = Path(os.environ.get("VIZIER_CONFIG", "config.yaml"))
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"FATAL configuration: {exc}", file=sys.stderr)
        return 2

    _configure_logging(config)
    env = dict(os.environ)

    try:
        door, audit = build(config, env)
    except ConfigError as exc:
        # Not a traceback: this is a message for a human at 1am on a phone.
        print(f"FATAL configuration: {exc}", file=sys.stderr)
        return 2

    # A redacted summary, so "what is actually running?" is answerable from the
    # container log without reading the code.
    LOG.info("wired: %s", json.dumps(config.redacted(), ensure_ascii=False))

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    audit.record(
        AuditEvent(
            actor="system",
            action="vizier.start",
            outcome="ok",
            reason=f"started with tiers {list(config.enabled_tiers())}",
            detail={"config": str(config_path)},
        )
    )
    LOG.info("polling telegram (long-poll, no inbound port)")

    try:
        door.run(lambda: _STOP)
    finally:
        audit.record(
            AuditEvent(
                actor="system",
                action="vizier.stop",
                outcome="ok",
                reason="stopped cleanly after a signal" if _STOP else "poll loop exited",
            )
        )
        LOG.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
