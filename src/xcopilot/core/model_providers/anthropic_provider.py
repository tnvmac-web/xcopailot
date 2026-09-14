"""Anthropic model provider implementation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx

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


class AnthropicProvider(ModelProviderBase):
    """Anthropic API provider."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.base_url = config.get("base_url") or "https://api.anthropic.com"
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.ANTHROPIC

    def _get_client(self):
        """Lazy initialize Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
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
        """Chat completion via Anthropic API."""
        client = self._get_client()

        # Convert messages to Anthropic format
        system_prompt = ""
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                anthropic_messages.append(
                    {
                        "role": msg.role,
                        "content": msg.content,
                    }
                )

        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        if stream:
            return self._stream_chat(client, kwargs)

        response = await client.messages.create(**kwargs)

        content = ""
        tool_calls = None
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        return ChatResponse(
            content=content,
            model=response.model,
            provider=ModelProvider.ANTHROPIC,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            finish_reason=response.stop_reason or "stop",
            tool_calls=tool_calls,
            raw_response=response.model_dump(),
        )

    async def _stream_chat(
        self,
        client,
        kwargs: dict,
    ) -> AsyncIterator[ChatResponse]:
        """Stream chat completion."""
        stream = await client.messages.create(**kwargs, stream=True)
        async for chunk in stream:
            if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
                yield ChatResponse(
                    content=chunk.delta.text,
                    model=kwargs["model"],
                    provider=ModelProvider.ANTHROPIC,
                    finish_reason="stop",
                )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Anthropic doesn't have embeddings API yet."""
        raise NotImplementedError("Anthropic does not currently offer embeddings API")

    async def list_models(self) -> list[ModelInfo]:
        """List available Anthropic models."""
        if self._models_cache:
            return self._models_cache

        known_models = [
            ModelInfo(
                id="claude-3-5-sonnet-20241022",
                name="Claude 3.5 Sonnet",
                provider=ModelProvider.ANTHROPIC,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                    ModelCapability.REASONING,
                ],
                context_window=200000,
                max_output_tokens=8192,
                pricing={"input": 3.00, "output": 15.00},
            ),
            ModelInfo(
                id="claude-3-5-haiku-20241022",
                name="Claude 3.5 Haiku",
                provider=ModelProvider.ANTHROPIC,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                ],
                context_window=200000,
                max_output_tokens=8192,
                pricing={"input": 0.80, "output": 4.00},
            ),
            ModelInfo(
                id="claude-3-opus-20240229",
                name="Claude 3 Opus",
                provider=ModelProvider.ANTHROPIC,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                    ModelCapability.REASONING,
                ],
                context_window=200000,
                max_output_tokens=4096,
                pricing={"input": 15.00, "output": 75.00},
            ),
            ModelInfo(
                id="claude-3-sonnet-20240229",
                name="Claude 3 Sonnet",
                provider=ModelProvider.ANTHROPIC,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                ],
                context_window=200000,
                max_output_tokens=4096,
                pricing={"input": 3.00, "output": 15.00},
            ),
            ModelInfo(
                id="claude-3-haiku-20240307",
                name="Claude 3 Haiku",
                provider=ModelProvider.ANTHROPIC,
                capabilities=[
                    ModelCapability.CHAT,
                    ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                    ModelCapability.VISION,
                ],
                context_window=200000,
                max_output_tokens=4096,
                pricing={"input": 0.25, "output": 1.25},
            ),
        ]

        self._models_cache = known_models
        return known_models

    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        if not self.api_key:
            return False
        try:
            self._get_client()
            # Anthropic doesn't have a simple health check endpoint
            # Just verify we can create a client
            return True
        except (httpx.HTTPError, AttributeError):
            return False


def register_anthropic(config: dict | None = None) -> AnthropicProvider:
    """Register Anthropic provider with registry."""
    config = config or {}
    provider = AnthropicProvider(config)
    registry.register(provider)
    return provider
