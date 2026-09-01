"""The configuration contract.

Three properties this module exists to guarantee, each traceable to a requirement:

* **No model name appears in code** (design.md D4, requirement N6). Every model
  identifier lives in ``config.yaml``. ``tests/test_no_model_names_in_code.py``
  fails the build if that slips.
* **$0 is enforced, not intended** (requirement N1). If an enabled tier points at
  a provider marked ``paid``, loading *fails* unless
  ``brains.allow_paid_providers`` is explicitly true.
* **Secrets are referenced by environment-variable NAME, never by value**
  (requirement R7.10, R12.1). Loading never reads a secret value, so no error
  message and no log line produced here can leak one.

Loading is **pure**: it does not touch the environment, the network or the disk
beyond reading the YAML file. Checking the environment is a separate, explicit
call (:func:`missing_env_vars`) so that tests can validate configuration without
credentials present.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

SUPPORTED_VERSION: Final[int] = 1

#: Prefixes and shapes of secrets known to this ecosystem. Used to fail loudly if
#: a real credential is ever pasted into ``config.yaml`` instead of an env-var
#: name. Deliberately conservative: known shapes only, because a generic
#: "looks random" heuristic produces false positives that teach people to ignore
#: the check — and a check that cries wolf is worse than no check.
SECRET_SHAPES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),  # Groq
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),  # GitHub fine-grained
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),  # GitHub classic
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),  # OpenAI-style
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),  # Google
    re.compile(r"\bglpat-[A-Za-z0-9_-]{15,}"),  # GitLab
    re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}"),  # Telegram bot token
)


class ConfigError(Exception):
    """Configuration is invalid. Raised with the offending path, never a value."""


# ─────────────────────────────────────────────────────────────────────────────
# Typed shapes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Provider:
    """How to reach a family of models. Adding one is one entry plus one adapter."""

    name: str
    kind: str
    base_url: str
    api_key_env: str | None
    paid: bool


@dataclass(frozen=True, slots=True)
class Tier:
    """Which model to use for a class of work.

    ``model`` is ``None`` while the tier is disabled. A tier may not be enabled
    without naming a model — that is the fail-closed posture (constraint 11):
    a half-configured brain must refuse to start rather than silently answer.
    """

    name: str
    provider: str
    model: str | None
    enabled: bool
    max_tokens: int
    temperature: float


@dataclass(frozen=True, slots=True)
class Brains:
    allow_paid_providers: bool
    providers: Mapping[str, Provider]
    tiers: Mapping[str, Tier]
    fallback: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class TelegramDoor:
    token_env: str
    owner_ids_env: str
    ack_after_seconds: int
    interim_after_seconds: int
    poll_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    token_env: str
    org: str
    allowed_repos: tuple[str, ...]
    protected_branches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Paths:
    memory_repo: Path
    database: Path
    audit_log: Path


@dataclass(frozen=True, slots=True)
class Limits:
    max_tool_calls_per_turn: int
    max_concurrent_dispatches: int
    approval_timeout_seconds: int
    turn_timeout_seconds: int


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str
    format: str
    redact_secrets: bool


@dataclass(frozen=True, slots=True)
class Config:
    version: int
    brains: Brains
    telegram: TelegramDoor
    github: GitHubConfig
    paths: Paths
    limits: Limits
    logging: LoggingConfig

    def enabled_tiers(self) -> tuple[str, ...]:
        """Tier names currently enabled, in declaration order."""
        return tuple(name for name, tier in self.brains.tiers.items() if tier.enabled)

    def required_env_vars(self) -> tuple[str, ...]:
        """Environment variable NAMES this configuration needs to run.

        Only providers backing an *enabled* tier are included: an unconfigured
        brain must not be able to block startup for a credential nothing uses.
        """
        names: list[str] = [
            self.telegram.token_env,
            self.telegram.owner_ids_env,
            self.github.token_env,
        ]
        for tier_name in self.enabled_tiers():
            provider = self.brains.providers[self.brains.tiers[tier_name].provider]
            if provider.api_key_env is not None:
                names.append(provider.api_key_env)
        # dict.fromkeys preserves order while de-duplicating
        return tuple(dict.fromkeys(names))

    def fallback_chain(self, tier: str) -> tuple[str, ...]:
        """Ordered tiers to try for ``tier``. Validated to be non-empty at load."""
        if tier not in self.brains.fallback:
            raise ConfigError(f"brains.fallback: no chain declared for tier {tier!r}")
        return self.brains.fallback[tier]

    def redacted(self) -> dict[str, Any]:
        """A representation safe to log.

        Contains env-var *names* only. No secret value ever enters this object,
        because no secret value is ever read during loading.
        """
        return {
            "version": self.version,
            "brains": {
                "allow_paid_providers": self.brains.allow_paid_providers,
                "providers": {
                    name: {
                        "kind": p.kind,
                        "base_url": p.base_url,
                        "api_key_env": p.api_key_env,
                        "paid": p.paid,
                    }
                    for name, p in self.brains.providers.items()
                },
                "tiers": {
                    name: {
                        "provider": t.provider,
                        "model": t.model,
                        "enabled": t.enabled,
                    }
                    for name, t in self.brains.tiers.items()
                },
            },
            "enabled_tiers": list(self.enabled_tiers()),
            "required_env_vars": list(self.required_env_vars()),
            "github": {
                "org": self.github.org,
                "allowed_repos": list(self.github.allowed_repos),
                "protected_branches": list(self.github.protected_branches),
            },
            "limits": {
                "max_tool_calls_per_turn": self.limits.max_tool_calls_per_turn,
                "max_concurrent_dispatches": self.limits.max_concurrent_dispatches,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Field readers — every failure names its path, never its value
# ─────────────────────────────────────────────────────────────────────────────


def _section(data: Mapping[str, Any], key: str, ctx: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ConfigError(f"{ctx}.{key}: expected a mapping, got {type(value).__name__}")
    return value


def _req_str(data: Mapping[str, Any], key: str, ctx: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{ctx}.{key}: expected a non-empty string")
    return value


def _opt_str(data: Mapping[str, Any], key: str, ctx: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{ctx}.{key}: expected a non-empty string or null")
    return value


def _req_int(data: Mapping[str, Any], key: str, ctx: str, *, minimum: int = 1) -> int:
    value = data.get(key)
    # bool is a subclass of int; reject it so `enabled: true` cannot pass as a count
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{ctx}.{key}: expected an integer")
    if value < minimum:
        raise ConfigError(f"{ctx}.{key}: must be >= {minimum}, got {value}")
    return value


def _req_bool(data: Mapping[str, Any], key: str, ctx: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{ctx}.{key}: expected a boolean")
    return value


def _req_float(data: Mapping[str, Any], key: str, ctx: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{ctx}.{key}: expected a number")
    return float(value)


def _req_str_list(data: Mapping[str, Any], key: str, ctx: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ConfigError(f"{ctx}.{key}: expected a non-empty list of strings")
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ConfigError(f"{ctx}.{key}[{index}]: expected a non-empty string")
        out.append(item)
    return tuple(out)


# ─────────────────────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────────────────────


def find_secret_shapes(text: str) -> tuple[str, ...]:
    """Names of secret shapes present in ``text``.

    Returns *shape descriptions*, never the matched text, so that a failure
    message can be logged and pasted into a PR without leaking the credential it
    just caught.
    """
    found: list[str] = []
    for pattern in SECRET_SHAPES:
        if pattern.search(text):
            found.append(pattern.pattern)
    return tuple(found)


def redact(text: str) -> str:
    """Replace anything secret-shaped with a marker.

    Used on every audit row and every log line before it is written. The audit log
    is the one thing that must record *everything*, which makes it the one thing
    most likely to capture a credential by accident.
    """
    for pattern in SECRET_SHAPES:
        text = pattern.sub("[REDACTED]", text)
    return text


def parse_config(raw: Mapping[str, Any]) -> Config:
    """Validate an already-parsed mapping into a :class:`Config`.

    Separated from :func:`load_config` so tests can exercise every validation
    branch without writing temporary files.
    """
    version = _req_int(raw, "version", "root")
    if version != SUPPORTED_VERSION:
        raise ConfigError(
            f"root.version: unsupported version {version}, expected {SUPPORTED_VERSION}"
        )

    brains_raw = _section(raw, "brains", "root")
    allow_paid = _req_bool(brains_raw, "allow_paid_providers", "brains")

    providers_raw = _section(brains_raw, "providers", "brains")
    if not providers_raw:
        raise ConfigError("brains.providers: at least one provider is required")
    providers: dict[str, Provider] = {}
    for name, body in providers_raw.items():
        ctx = f"brains.providers.{name}"
        if not isinstance(body, Mapping):
            raise ConfigError(f"{ctx}: expected a mapping")
        providers[str(name)] = Provider(
            name=str(name),
            kind=_req_str(body, "kind", ctx),
            base_url=_req_str(body, "base_url", ctx),
            api_key_env=_opt_str(body, "api_key_env", ctx),
            paid=_req_bool(body, "paid", ctx),
        )

    tiers_raw = _section(brains_raw, "tiers", "brains")
    if not tiers_raw:
        raise ConfigError("brains.tiers: at least one tier is required")
    tiers: dict[str, Tier] = {}
    for name, body in tiers_raw.items():
        ctx = f"brains.tiers.{name}"
        if not isinstance(body, Mapping):
            raise ConfigError(f"{ctx}: expected a mapping")
        provider_name = _req_str(body, "provider", ctx)
        if provider_name not in providers:
            raise ConfigError(f"{ctx}.provider: unknown provider {provider_name!r}")
        enabled = _req_bool(body, "enabled", ctx)
        model = _opt_str(body, "model", ctx)

        # Fail closed: a tier that is on must say what it runs.
        if enabled and model is None:
            raise ConfigError(f"{ctx}: enabled tier must name a model (fail-closed, constraint 11)")

        # $0 is enforced here, not merely documented (requirement N1).
        if enabled and providers[provider_name].paid and not allow_paid:
            raise ConfigError(
                f"{ctx}: provider {provider_name!r} is marked paid but "
                "brains.allow_paid_providers is false — a paid brain requires a "
                "written owner exception (design.md §7 item 7)"
            )

        tiers[str(name)] = Tier(
            name=str(name),
            provider=provider_name,
            model=model,
            enabled=enabled,
            max_tokens=_req_int(body, "max_tokens", ctx),
            temperature=_req_float(body, "temperature", ctx),
        )

    fallback_raw = _section(brains_raw, "fallback", "brains")
    fallback: dict[str, tuple[str, ...]] = {}
    for name, chain in fallback_raw.items():
        ctx = f"brains.fallback.{name}"
        if str(name) not in tiers:
            raise ConfigError(f"{ctx}: unknown tier {name!r}")
        entries = _req_str_list({"chain": chain}, "chain", ctx)
        for entry in entries:
            if entry not in tiers:
                raise ConfigError(f"{ctx}: unknown tier {entry!r} in chain")
        fallback[str(name)] = entries
    missing_chains = sorted(set(tiers) - set(fallback))
    if missing_chains:
        raise ConfigError(f"brains.fallback: no chain declared for tiers {missing_chains}")

    door_raw = _section(raw, "door", "root")
    telegram_raw = _section(door_raw, "telegram", "door")
    telegram = TelegramDoor(
        token_env=_req_str(telegram_raw, "token_env", "door.telegram"),
        owner_ids_env=_req_str(telegram_raw, "owner_ids_env", "door.telegram"),
        ack_after_seconds=_req_int(telegram_raw, "ack_after_seconds", "door.telegram"),
        interim_after_seconds=_req_int(telegram_raw, "interim_after_seconds", "door.telegram"),
        poll_timeout_seconds=_req_int(telegram_raw, "poll_timeout_seconds", "door.telegram"),
    )

    github_raw = _section(raw, "github", "root")
    github = GitHubConfig(
        token_env=_req_str(github_raw, "token_env", "github"),
        org=_req_str(github_raw, "org", "github"),
        allowed_repos=_req_str_list(github_raw, "allowed_repos", "github"),
        protected_branches=_req_str_list(github_raw, "protected_branches", "github"),
    )
    # The one branch that must never be writable. Belt and braces alongside the
    # `protect-main` ruleset and the token's own permissions (design.md D7).
    if "main" not in github.protected_branches:
        raise ConfigError("github.protected_branches: must include 'main' (requirement R7.4)")

    paths_raw = _section(raw, "paths", "root")
    paths = Paths(
        memory_repo=Path(_req_str(paths_raw, "memory_repo", "paths")),
        database=Path(_req_str(paths_raw, "database", "paths")),
        audit_log=Path(_req_str(paths_raw, "audit_log", "paths")),
    )

    limits_raw = _section(raw, "limits", "root")
    limits = Limits(
        max_tool_calls_per_turn=_req_int(limits_raw, "max_tool_calls_per_turn", "limits"),
        max_concurrent_dispatches=_req_int(limits_raw, "max_concurrent_dispatches", "limits"),
        approval_timeout_seconds=_req_int(limits_raw, "approval_timeout_seconds", "limits"),
        turn_timeout_seconds=_req_int(limits_raw, "turn_timeout_seconds", "limits"),
    )

    logging_raw = _section(raw, "logging", "root")
    logging_config = LoggingConfig(
        level=_req_str(logging_raw, "level", "logging"),
        format=_req_str(logging_raw, "format", "logging"),
        redact_secrets=_req_bool(logging_raw, "redact_secrets", "logging"),
    )
    if not logging_config.redact_secrets:
        raise ConfigError("logging.redact_secrets: must be true (requirement R7.10)")

    return Config(
        version=version,
        brains=Brains(
            allow_paid_providers=allow_paid,
            providers=providers,
            tiers=tiers,
            fallback=fallback,
        ),
        telegram=telegram,
        github=github,
        paths=paths,
        limits=limits,
        logging=logging_config,
    )


def load_config(path: str | Path) -> Config:
    """Read and validate ``config.yaml``.

    Does not read the environment and does not resolve secrets — see
    :func:`missing_env_vars`.
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config file {file_path}: {exc}") from exc

    shapes = find_secret_shapes(text)
    if shapes:
        raise ConfigError(
            f"{file_path}: appears to contain {len(shapes)} secret value(s) matching "
            f"{list(shapes)}. Secrets are referenced by environment-variable NAME "
            "only; remove the value and use `api_key_env` / `*_env`."
        )

    loaded = yaml.safe_load(text)
    if not isinstance(loaded, Mapping):
        raise ConfigError(f"{file_path}: expected a mapping at the top level")
    return parse_config(loaded)


def missing_env_vars(config: Config, env: Mapping[str, str]) -> tuple[str, ...]:
    """Names of required environment variables that are absent or empty.

    Returns **names**, never values, so the result is safe to log and safe to
    show the owner.
    """
    return tuple(name for name in config.required_env_vars() if not env.get(name, "").strip())
