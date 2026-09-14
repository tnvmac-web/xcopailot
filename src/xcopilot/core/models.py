"""Model provider abstraction and unified interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum

import httpx
import openai


class APIMode(Enum):
    """API execution modes for model providers.

    Each provider resolves to one of these modes based on its API shape.
    See X-Copilot provider-runtime docs for details.
    """

    CHAT_COMPLETIONS = "chat_completions"
    CODEX_RESPONSES = "codex_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"

    @classmethod
    def from_provider(cls, provider_type: ModelProvider) -> APIMode:
        """Resolve API mode for a given provider."""
        mapping = {
            ModelProvider.OPENAI: cls.CHAT_COMPLETIONS,
            ModelProvider.NVIDIA: cls.CHAT_COMPLETIONS,
            ModelProvider.OPENROUTER: cls.CHAT_COMPLETIONS,
            ModelProvider.OLLAMA: cls.CHAT_COMPLETIONS,
            ModelProvider.LMSTUDIO: cls.CHAT_COMPLETIONS,
            ModelProvider.ANTHROPIC: cls.ANTHROPIC_MESSAGES,
        }
        return mapping.get(provider_type, cls.CHAT_COMPLETIONS)


class ModelProvider(Enum):
    """Supported model providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    OPENROUTER = "openrouter"
    NVIDIA = "nvidia"
    CUSTOM = "custom"


class ModelCapability(Enum):
    """Model capabilities."""

    CHAT = "chat"
    STREAMING = "streaming"
    EMBEDDINGS = "embeddings"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    REASONING = "reasoning"


@dataclass
class ModelInfo:
    """Information about a model."""

    id: str
    name: str
    provider: ModelProvider
    api_mode: APIMode = APIMode.CHAT_COMPLETIONS
    capabilities: list[ModelCapability] = field(default_factory=list)
    context_window: int = 4096
    max_output_tokens: int = 4096
    pricing: dict = field(default_factory=dict)  # per 1M tokens
    metadata: dict = field(default_factory=dict)


@dataclass
class ChatMessage:
    """Chat message."""

    role: str  # system, user, assistant, tool
    content: str
    name: str | None = None
    tool_calls: list | None = None
    tool_call_id: str | None = None


@dataclass
class ChatResponse:
    """Chat completion response."""

    content: str
    model: str
    provider: ModelProvider
    api_mode: APIMode = APIMode.CHAT_COMPLETIONS
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str = "stop"
    tool_calls: list | None = None
    raw_response: dict | None = None


@dataclass
class EmbeddingResponse:
    """Embedding response."""

    embeddings: list[list[float]]
    model: str
    provider: ModelProvider
    api_mode: APIMode = APIMode.CHAT_COMPLETIONS
    usage: dict = field(default_factory=dict)


class ModelProviderBase(ABC):
    """Base class for model providers."""

    def __init__(self, config: dict):
        self.config = config
        self._models_cache: list[ModelInfo] = []
        self.api_mode = APIMode.from_provider(self.provider_type)

    @property
    @abstractmethod
    def provider_type(self) -> ModelProvider:
        """Return the provider type."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list | None = None,
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[ChatResponse]:
        """Chat completion."""

    @abstractmethod
    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is available."""

    def estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for a completion."""
        models = {m.id: m for m in self._models_cache}
        if model in models:
            pricing = models[model].pricing
            input_cost = pricing.get("input", 0) * prompt_tokens / 1_000_000
            output_cost = pricing.get("output", 0) * completion_tokens / 1_000_000
            return input_cost + output_cost
        return 0.0


class ProviderRegistry:
    """Registry of model providers."""

    def __init__(self):
        self._providers: dict[ModelProvider, ModelProviderBase] = {}
        self._default_provider: ModelProvider | None = None
        self._fallback_chain: list[ModelProvider] = []

    def register(self, provider: ModelProviderBase) -> None:
        """Register a provider."""
        self._providers[provider.provider_type] = provider

    def unregister(self, provider_type: ModelProvider) -> None:
        """Unregister a provider."""
        self._providers.pop(provider_type, None)

    def get(self, provider_type: ModelProvider) -> ModelProviderBase | None:
        """Get a provider by type."""
        return self._providers.get(provider_type)

    def set_default(self, provider_type: ModelProvider) -> None:
        """Set default provider."""
        if provider_type in self._providers:
            self._default_provider = provider_type

    def set_fallback_chain(self, chain: list[ModelProvider]) -> None:
        """Set fallback chain."""
        self._fallback_chain = [p for p in chain if p in self._providers]

    def get_default(self) -> ModelProviderBase | None:
        """Get default provider. Raises if no default configured and multiple providers exist."""
        if self._default_provider:
            return self._providers.get(self._default_provider)
        # No default set — if only one provider, return it
        if len(self._providers) == 1:
            return next(iter(self._providers.values()))
        raise RuntimeError(
            "No default provider configured and multiple providers registered. "
            f"Set a default or call set_default(). Providers: {list(self._providers.keys())}"
        )

    async def chat_with_fallback(
        self,
        messages: list[ChatMessage],
        model: str,
        **kwargs,
    ) -> ChatResponse:
        """Chat with fallback chain."""
        # Try default provider first
        providers_to_try = []
        if self._default_provider:
            providers_to_try.append(self._default_provider)
        providers_to_try.extend(self._fallback_chain)

        last_error = None
        for provider_type in providers_to_try:
            provider = self._providers.get(provider_type)
            if not provider:
                continue
            try:
                # Check if provider supports the model
                models = await provider.list_models()
                if any(m.id == model for m in models):
                    return await provider.chat(messages, model, **kwargs)
            except (
                httpx.HTTPError,
                openai.APIError,
                openai.APIConnectionError,
                ValueError,
                RuntimeError,
            ) as e:
                last_error = e
                continue

        raise RuntimeError(f"No provider available for model {model}: {last_error}")

    async def list_all_models(self) -> dict[ModelProvider, list[ModelInfo]]:
        """List models from all providers."""
        result = {}
        for provider_type, provider in self._providers.items():
            try:
                result[provider_type] = await provider.list_models()
            except (httpx.HTTPError, ValueError, RuntimeError):
                result[provider_type] = []
        return result


# Global registry instance
registry = ProviderRegistry()
