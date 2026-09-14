"""NVIDIA model provider implementation using OpenAI-compatible API."""

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


class NVIDIAProvider(ModelProviderBase):
    """NVIDIA API provider (OpenAI-compatible)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.environ.get("NVIDIA_API_KEY")
        # NVIDIA's OpenAI-compatible endpoint
        self.base_url = config.get("base_url") or "https://integrate.api.nvidia.com/v1"
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.NVIDIA

    def _get_client(self):
        """Lazy initialize NVIDIA client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
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
        """Chat completion via NVIDIA API."""
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
            provider=ModelProvider.NVIDIA,
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
                        provider=ModelProvider.NVIDIA,
                        finish_reason=choice.finish_reason or "stop",
                    )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings via NVIDIA API."""
        client = self._get_client()
        response = await client.embeddings.create(
            model=model,
            input=texts,
        )
        return EmbeddingResponse(
            embeddings=[d.embedding for d in response.data],
            model=response.model,
            provider=ModelProvider.NVIDIA,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if response.usage
            else {},
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available NVIDIA models."""
        if self._models_cache:
            return self._models_cache

        try:
            response = await self._get_client().models.list()
            live_models = [
                ModelInfo(
                    id=item.id,
                    name=item.id,
                    provider=ModelProvider.NVIDIA,
                    capabilities=[ModelCapability.CHAT, ModelCapability.STREAMING],
                    context_window=128000,
                    max_output_tokens=8192,
                )
                for item in response.data
            ]
            if live_models:
                self._models_cache = live_models
                return live_models
        except (openai.APIError, openai.APIConnectionError, ValueError):
            pass

        # Known NVIDIA models (NVIDIA provides various models via their API)
        known_models = [
            ModelInfo(
                id="nvidia/nemotron-3-ultra",
                name="Nemotron 3 Ultra",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.REASONING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},  # Free during preview
            ),
            ModelInfo(
                id="nvidia/nemotron-3-ultra-55b",
                name="Nemotron 3 Ultra 55B",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.REASONING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="nvidia/nemotron-4-340b",
                name="Nemotron 4 340B",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.REASONING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="meta/llama-3.1-405b-instruct",
                name="Llama 3.1 405B Instruct",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.REASONING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="meta/llama-3.1-70b-instruct",
                name="Llama 3.1 70B Instruct",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="meta/llama-3.1-8b-instruct",
                name="Llama 3.1 8B Instruct",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="mistralai/mistral-large",
                name="Mistral Large",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="mistralai/mixtral-8x22b-instruct",
                name="Mixtral 8x22B Instruct",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="google/gemma-2-27b",
                name="Gemma 2 27B",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
            ModelInfo(
                id="google/gemma-2-9b",
                name="Gemma 2 9B",
                provider=ModelProvider.NVIDIA,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                context_window=128000,
                max_output_tokens=8192,
                pricing={"input": 0.0, "output": 0.0},
            ),
        ]

        self._models_cache = known_models
        return known_models

    async def health_check(self) -> bool:
        """Check if NVIDIA API is accessible."""
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except (openai.APIError, openai.APIConnectionError):
            return False


def register_nvidia(config: dict | None = None) -> NVIDIAProvider:
    """Register NVIDIA provider with registry."""
    config = config or {}
    provider = NVIDIAProvider(config)
    registry.register(provider)
    return provider
