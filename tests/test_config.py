"""Tests for the configuration contract.

Emphasis is on the three guarantees the module exists for: no model names in
code, $0 enforced, and secrets referenced by name only. Every negative case
asserts the *failure*, because a validator that never rejects anything is not a
validator.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from vizier.config import (
    SUPPORTED_VERSION,
    ConfigError,
    find_secret_shapes,
    load_config,
    missing_env_vars,
    parse_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

MINIMAL: dict[str, Any] = {
    "version": SUPPORTED_VERSION,
    "brains": {
        "allow_paid_providers": False,
        "providers": {
            "free_provider": {
                "kind": "openai_compatible",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "VIZIER_TEST_KEY",
                "paid": False,
            },
            "paid_provider": {
                "kind": "openai_compatible",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "VIZIER_PAID_KEY",
                "paid": True,
            },
        },
        "tiers": {
            "thinking": {
                "provider": "free_provider",
                "model": None,
                "enabled": False,
                "max_tokens": 4096,
                "temperature": 0.3,
            },
        },
        "fallback": {"thinking": ["thinking"]},
    },
    "door": {
        "telegram": {
            "token_env": "VIZIER_TELEGRAM_TOKEN",
            "owner_ids_env": "VIZIER_TELEGRAM_OWNER_ID",
            "ack_after_seconds": 3,
            "interim_after_seconds": 10,
            "poll_timeout_seconds": 30,
        }
    },
    "github": {
        "token_env": "VIZIER_GITHUB_TOKEN",
        "org": "empireenglishcommunity-glitch",
        "allowed_repos": ["macal-ai-model"],
        "protected_branches": ["main", "master"],
    },
    "paths": {
        "memory_repo": "/opt/macal-vizier/macal-memory",
        "database": "/opt/macal-vizier/data/vizier.db",
        "audit_log": "/opt/macal-vizier/logs/audit.jsonl",
    },
    "limits": {
        "max_tool_calls_per_turn": 5,
        "max_concurrent_dispatches": 1,
        "approval_timeout_seconds": 300,
        "turn_timeout_seconds": 600,
    },
    "logging": {"level": "INFO", "format": "json", "redact_secrets": True},
}


def cfg(**overrides: Any) -> dict[str, Any]:
    """A deep copy of MINIMAL with top-level sections replaced."""
    data = copy.deepcopy(MINIMAL)
    data.update(copy.deepcopy(overrides))
    return data


# ─── the real file must be valid ────────────────────────────────────────────


def test_shipped_config_yaml_loads() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    assert config.version == SUPPORTED_VERSION


def test_shipped_config_ships_every_tier_disabled() -> None:
    """Fail closed: no brain adapter exists until task 1.3, so nothing may claim
    to be usable. A restored or freshly cloned system comes up inert on purpose,
    so an operator notices "nothing is running" rather than getting a
    half-configured brain."""
    config = load_config(REPO_ROOT / "config.yaml")
    assert config.enabled_tiers() == ()


def test_shipped_config_declares_a_fallback_chain_for_every_tier() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    for tier in config.brains.tiers:
        assert config.fallback_chain(tier)


def test_shipped_config_protects_main() -> None:
    config = load_config(REPO_ROOT / "config.yaml")
    assert "main" in config.github.protected_branches


# ─── $0 is enforced, not intended (N1) ─────────────────────────────────────


def test_enabled_paid_provider_is_refused() -> None:
    data = cfg()
    data["brains"]["tiers"]["deep"] = {
        "provider": "paid_provider",
        "model": "some-model",
        "enabled": True,
        "max_tokens": 8192,
        "temperature": 0.3,
    }
    data["brains"]["fallback"]["deep"] = ["deep"]
    with pytest.raises(ConfigError, match="allow_paid_providers"):
        parse_config(data)


def test_enabled_paid_provider_is_allowed_with_explicit_exception() -> None:
    data = cfg()
    data["brains"]["allow_paid_providers"] = True
    data["brains"]["tiers"]["deep"] = {
        "provider": "paid_provider",
        "model": "some-model",
        "enabled": True,
        "max_tokens": 8192,
        "temperature": 0.3,
    }
    data["brains"]["fallback"]["deep"] = ["deep"]
    assert parse_config(data).enabled_tiers() == ("deep",)


def test_disabled_paid_provider_is_ignored() -> None:
    """A declared-but-off paid provider must not block startup."""
    assert parse_config(cfg()).enabled_tiers() == ()


# ─── fail closed ───────────────────────────────────────────────────────────


def test_enabled_tier_without_a_model_is_refused() -> None:
    data = cfg()
    data["brains"]["tiers"]["thinking"]["enabled"] = True
    with pytest.raises(ConfigError, match="must name a model"):
        parse_config(data)


def test_tier_with_unknown_provider_is_refused() -> None:
    data = cfg()
    data["brains"]["tiers"]["thinking"]["provider"] = "nonexistent"
    with pytest.raises(ConfigError, match="unknown provider"):
        parse_config(data)


def test_fallback_chain_referencing_unknown_tier_is_refused() -> None:
    data = cfg()
    data["brains"]["fallback"]["thinking"] = ["thinking", "ghost"]
    with pytest.raises(ConfigError, match="unknown tier 'ghost'"):
        parse_config(data)


def test_tier_without_a_fallback_chain_is_refused() -> None:
    data = cfg()
    data["brains"]["tiers"]["extra"] = {
        "provider": "free_provider",
        "model": None,
        "enabled": False,
        "max_tokens": 100,
        "temperature": 0.0,
    }
    with pytest.raises(ConfigError, match="no chain declared"):
        parse_config(data)


def test_unprotected_main_is_refused() -> None:
    data = cfg()
    data["github"]["protected_branches"] = ["master"]
    with pytest.raises(ConfigError, match="must include 'main'"):
        parse_config(data)


def test_disabling_secret_redaction_is_refused() -> None:
    data = cfg()
    data["logging"]["redact_secrets"] = False
    with pytest.raises(ConfigError, match="redact_secrets"):
        parse_config(data)


def test_unsupported_version_is_refused() -> None:
    data = cfg()
    data["version"] = 99
    with pytest.raises(ConfigError, match="unsupported version"):
        parse_config(data)


def test_boolean_is_not_accepted_as_an_integer() -> None:
    """`bool` subclasses `int` in Python; `max_tokens: true` must not pass."""
    data = cfg()
    data["limits"]["max_tool_calls_per_turn"] = True
    with pytest.raises(ConfigError, match="expected an integer"):
        parse_config(data)


# ─── secrets are names, never values ───────────────────────────────────────


def test_secret_shapes_are_detected() -> None:
    samples = (
        "VIZIER_GROQ_API_KEY=gsk_" + "a" * 40,
        "token: github_pat_" + "b" * 40,
        "key: ghp_" + "c" * 40,
        "openai: sk-" + "d" * 40,
        "google: AIza" + "e" * 35,
        "gitlab: glpat-" + "f" * 20,
        "telegram: 12345678:AA" + "g" * 33,
    )
    for sample in samples:
        assert find_secret_shapes(sample), sample


def test_secret_shape_report_never_contains_the_secret() -> None:
    """The failure message is pasted into PRs, so it must not leak what it caught."""
    secret = "gsk_" + "z" * 40
    shapes = find_secret_shapes(f"key: {secret}")
    assert shapes
    assert all(secret not in shape for shape in shapes)


def test_ordinary_config_text_is_not_flagged() -> None:
    assert find_secret_shapes("api_key_env: VIZIER_GROQ_API_KEY") == ()


def test_shipped_config_yaml_contains_no_secret_values() -> None:
    text = (REPO_ROOT / "config.yaml").read_text(encoding="utf-8")
    assert find_secret_shapes(text) == ()


def test_env_example_contains_no_values() -> None:
    """`.env.example` is committed, so every assignment must be empty."""
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assigned = [
        line
        for line in lines
        if not line.lstrip().startswith("#") and "=" in line and line.split("=", 1)[1].strip()
    ]
    assert assigned == [], f"values present in .env.example: {assigned}"


def test_config_with_a_pasted_secret_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    original = (REPO_ROOT / "config.yaml").read_text(encoding="utf-8")
    bad.write_text(
        original.replace("api_key_env: VIZIER_GROQ_API_KEY", "api_key_env: gsk_" + "x" * 40)
    )
    with pytest.raises(ConfigError, match="secret value"):
        load_config(bad)


# ─── environment reporting ─────────────────────────────────────────────────


def test_required_env_vars_excludes_disabled_tiers() -> None:
    config = parse_config(cfg())
    assert "VIZIER_TEST_KEY" not in config.required_env_vars()
    assert "VIZIER_TELEGRAM_TOKEN" in config.required_env_vars()
    assert "VIZIER_GITHUB_TOKEN" in config.required_env_vars()


def test_required_env_vars_includes_enabled_tier_provider_key() -> None:
    data = cfg()
    data["brains"]["tiers"]["thinking"].update({"enabled": True, "model": "some-model"})
    assert "VIZIER_TEST_KEY" in parse_config(data).required_env_vars()


def test_missing_env_vars_reports_names_only() -> None:
    config = parse_config(cfg())
    missing = missing_env_vars(config, {})
    assert "VIZIER_TELEGRAM_TOKEN" in missing
    assert missing_env_vars(config, dict.fromkeys(config.required_env_vars(), "x")) == ()


def test_whitespace_only_env_var_counts_as_missing() -> None:
    config = parse_config(cfg())
    env = dict.fromkeys(config.required_env_vars(), "   ")
    assert missing_env_vars(config, env) == config.required_env_vars()


def test_redacted_view_contains_names_not_values() -> None:
    config = parse_config(cfg())
    rendered = repr(config.redacted())
    assert "VIZIER_TELEGRAM_TOKEN" in rendered
    assert find_secret_shapes(rendered) == ()


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read config file"):
        load_config(tmp_path / "absent.yaml")
