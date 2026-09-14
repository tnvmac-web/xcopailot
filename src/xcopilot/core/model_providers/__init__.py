"""Model providers package init."""

from __future__ import annotations

from xcopilot.core.model_providers.anthropic_provider import register_anthropic
from xcopilot.core.model_providers.lmstudio_provider import register_lmstudio
from xcopilot.core.model_providers.nvidia_provider import register_nvidia
from xcopilot.core.model_providers.ollama_provider import register_ollama
from xcopilot.core.model_providers.openai_provider import register_openai
from xcopilot.core.model_providers.openrouter_provider import register_openrouter
from xcopilot.core.models import APIMode

__all__ = [
    "register_anthropic",
    "register_lmstudio",
    "register_nvidia",
    "register_ollama",
    "register_openai",
    "register_openrouter",
]


PROVIDER_API_MODES = {
    "openai": APIMode.CHAT_COMPLETIONS,
    "nvidia": APIMode.CHAT_COMPLETIONS,
    "openrouter": APIMode.CHAT_COMPLETIONS,
    "ollama": APIMode.CHAT_COMPLETIONS,
    "lmstudio": APIMode.CHAT_COMPLETIONS,
    "anthropic": APIMode.ANTHROPIC_MESSAGES,
}


def register_all_providers(config: dict | None = None) -> None:
    """Register all available model providers."""
    config = config or {}

    # Register providers with their configs
    if config.get("openai"):
        register_openai(config["openai"])
    if config.get("anthropic"):
        register_anthropic(config["anthropic"])
    if config.get("ollama"):
        register_ollama(config["ollama"])
    if config.get("lmstudio"):
        register_lmstudio(config["lmstudio"])
    if config.get("openrouter"):
        register_openrouter(config["openrouter"])
    if config.get("nvidia"):
        register_nvidia(config["nvidia"])

    # Auto-register Ollama and LM Studio if running (no API key needed)
    # This allows local models to work out of the box
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Can't run async here, will be checked on first use
            pass
    except (RuntimeError, AttributeError):
        pass
