"""The one place Gusset constructs its chat model.

An unattended custodian must outlast provider blips: a 529 at 2am is
routine weather, not a reason to fail a workflow run. The SDK's default
2 retries proved too few in CI (observed: atlas run killed by a single
overload burst), so every workflow gets the same patient client.
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_MODEL = "claude-sonnet-5"


def make_model(name: str | None = None) -> BaseChatModel:
    """Primary model with a same-provider fallback tier.

    Dogfood finding (2026-08-18): a sustained Opus-tier 529 storm outlasted
    8 retries while Sonnet answered instantly — capacity incidents are
    often tier-scoped, so the right response is to change tiers, not to
    keep retrying into the same wall. with_fallbacks hands the invocation
    to the fallback only after the primary's retries are exhausted.
    """
    from langchain_anthropic import ChatAnthropic

    primary_name = name or os.environ.get("GUSSET_MODEL", DEFAULT_MODEL)
    fallback_name = os.environ.get("GUSSET_FALLBACK_MODEL", FALLBACK_MODEL)
    primary = ChatAnthropic(
        model=primary_name,
        max_retries=8,       # exponential backoff; rides out 529 bursts
        timeout=300.0,
    )
    if fallback_name in ("", "none", primary_name):
        return primary
    fallback = ChatAnthropic(model=fallback_name, max_retries=8, timeout=300.0)
    return primary.with_fallbacks([fallback])
