"""Build brains from configuration. The only place adapters are chosen.

This is the concrete shape of N6: **adding a provider is one adapter plus one
config entry.** The mapping below is the entire cost of a new provider, and
nothing outside this file learns its name.

Two rules enforced here rather than trusted:

* An **enabled** tier whose provider needs a key, with no key in the environment,
  is a configuration error at startup — not a mystery failure on the first real
  turn. Fail loudly at boot; the alternative is discovering it when the owner asks
  a question.
* A **disabled** tier builds nothing. A restored system comes up inert on purpose.
"""

from __future__ import annotations

from collections.abc import Mapping

from vizier.brains.base import Brain
from vizier.brains.local_daemon import LocalDaemonBrain
from vizier.brains.openai_compatible import OpenAICompatibleBrain
from vizier.config import Config, ConfigError

#: provider ``kind`` -> adapter. The whole extension point.
KINDS = ("openai_compatible", "local_daemon")


def build_brains(config: Config, env: Mapping[str, str]) -> dict[str, Brain]:
    """One :class:`Brain` per **enabled** tier.

    Raises :class:`ConfigError` naming the tier and the missing variable — never
    the value.
    """
    brains: dict[str, Brain] = {}

    for tier_name in config.enabled_tiers():
        tier = config.brains.tiers[tier_name]
        provider = config.brains.providers[tier.provider]

        if tier.model is None:  # pragma: no cover - parse_config already refuses this
            raise ConfigError(f"brains.tiers.{tier_name}: enabled tier has no model")

        api_key: str | None = None
        if provider.api_key_env is not None:
            api_key = env.get(provider.api_key_env, "").strip() or None
            if api_key is None:
                raise ConfigError(
                    f"brains.tiers.{tier_name}: provider {provider.name!r} needs "
                    f"environment variable {provider.api_key_env} and it is missing "
                    "or empty"
                )

        if provider.kind == "openai_compatible":
            brains[tier_name] = OpenAICompatibleBrain(
                provider=provider.name,
                base_url=provider.base_url,
                model=tier.model,
                api_key=api_key,
            )
        elif provider.kind == "local_daemon":
            brains[tier_name] = LocalDaemonBrain(
                provider=provider.name,
                base_url=provider.base_url,
                model=tier.model,
            )
        else:
            raise ConfigError(
                f"brains.providers.{provider.name}.kind: unsupported kind "
                f"{provider.kind!r}; known kinds are {list(KINDS)}"
            )

    return brains
