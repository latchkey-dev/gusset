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


def make_model(name: str | None = None) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=name or os.environ.get("GUSSET_MODEL", DEFAULT_MODEL),
        max_retries=8,       # exponential backoff; rides out 529 bursts
        timeout=300.0,
    )
