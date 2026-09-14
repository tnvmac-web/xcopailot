"""OpenAI model provider implementation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import openai

from xcopilot.core.models import (
    ChatMessage,
    ChatResponse,
    EmbeddingResponse,
    ModelCapability,
    ModelInfo,
    ModelProvider,
    ModelProviderBase,
    registry,
)


class OpenAIProvider(ModelProviderBase):
    """OpenAI API provider."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        self.base_url = config.get("base_url") or "https://api.openai.com/v1"
        self.organization = config.get("organization")
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.OPENAI

    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    organization=self.organization,
                )
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list | None = None,
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[ChatResponse]:
        """Chat completion via OpenAI API."""
        client = self._get_client()

        # Convert messages to OpenAI format
        openai_messages = []
        for msg in messages:
            openai_msg = {"role": msg.role, "content": msg.content}
            if msg.name:
                openai_msg["name"] = msg.name
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
            openai_messages.append(openai_msg)

        kwargs = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if stream:
            return self._stream_chat(client, kwargs)

        response = await client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        return ChatResponse(
            content=choice.message.content or "",
            model=response.model,
            provider=ModelProvider.OPENAI,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if response.usage
            else {},
            finish_reason=choice.finish_reason,
            tool_calls=choice.message.tool_calls,
            raw_response=response.model_dump(),
        )

    async def _stream_chat(
        self,
        client,
        kwargs: dict,
    ) -> AsyncIterator[ChatResponse]:
        """Stream chat completion."""
        stream = await client.chat.completions.create(**kwargs, stream=True)
        async for chunk in stream:
            if chunk.choices:
                choice = chunk.choices[0]
                if choice.delta.content:
                    yield ChatResponse(
                        content=choice.delta.content,
                        model=chunk.model,
                        provider=ModelProvider.OPENAI,
                        finish_reason=choice.finish_reason or "stop",
                    )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings via OpenAI API."""
        client = self._get_client()
        response = await client.embeddings.create(
            model=model,
            input=texts,
        )
        return EmbeddingResponse(
            embeddings=[d.embedding for d in response.data],
            model=response.model,
            provider=ModelProvider.OPENAI,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if response.usage
            else {},
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available OpenAI models."""
        if self._models_cache:
            return self._models_cache

        # Known OpenAI models with capabilities
        known_models = [
            ModelInfo(
                id="gpt-4o",
                name="GPT-4o",
                provider=ModelProvider.OPENAI,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                    ModelCapability.REASONING,
                ],
                context_window=128000,
                max_output_tokens=16384,
                pricing={"input": 2.50, "output": 10.00},
            ),
            ModelInfo(
                id="gpt-4o-mini",
                name="GPT-4o Mini",
                provider=ModelProvider.OPENAI,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                ],
                context_window=128000,
                max_output_tokens=16384,
                pricing={"input": 0.15, "output": 0.60},
            ),
            ModelInfo(
                id="gpt-4-turbo",
                name="GPT-4 Turbo",
                provider=ModelProvider.OPENAI,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                ],
                context_window=128000,
                max_output_tokens=4096,
                pricing={"input": 10.00, "output": 30.00},
            ),
            ModelInfo(
                id="gpt-3.5-turbo",
                name="GPT-3.5 Turbo",
                provider=ModelProvider.OPENAI,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=16384,
                max_output_tokens=4096,
                pricing={"input": 0.50, "output": 1.50},
            ),
            ModelInfo(
                id="text-embedding-3-large",
                name="Text Embedding 3 Large",
                provider=ModelProvider.OPENAI,
                capabilities=[ModelCapability.EMBEDDINGS],
                context_window=8191,
                pricing={"input": 0.13},
            ),
            ModelInfo(
                id="text-embedding-3-small",
                name="Text Embedding 3 Small",
                provider=ModelProvider.OPENAI,
                capabilities=[ModelCapability.EMBEDDINGS],
                context_window=8191,
                pricing={"input": 0.02},
            ),
            ModelInfo(
                id="text-embedding-ada-002",
                name="Text Embedding Ada 002",
                provider=ModelProvider.OPENAI,
                capabilities=[ModelCapability.EMBEDDINGS],
                context_window=8191,
                pricing={"input": 0.10},
            ),
        ]

        self._models_cache = known_models
        return known_models

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except (openai.APIError, openai.APIConnectionError):
            return False


def register_openai(config: dict | None = None) -> OpenAIProvider:
    """Register OpenAI provider with registry."""
    config = config or {}
    provider = OpenAIProvider(config)
    registry.register(provider)
    return provider
