"""OpenRouter model provider implementation (access to 100+ models)."""

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


class OpenRouterProvider(ModelProviderBase):
    """OpenRouter API provider (unified access to many models)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key") or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = config.get("base_url") or "https://openrouter.ai/api/v1"
        self.app_name = config.get("app_name") or "X-Copilot"
        self.app_url = config.get("app_url") or "https://xcopilot.ai"
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.OPENROUTER

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": self.app_url,
                    "X-Title": self.app_name,
                },
                timeout=120.0,
            )
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
        """Chat completion via OpenRouter API."""
        client = self._get_client()

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

        payload = {
            "model": model,
            "messages": openai_messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stream:
            return self._stream_chat(client, payload)

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return ChatResponse(
            content=choice["message"]["content"] or "",
            model=data["model"],
            provider=ModelProvider.OPENROUTER,
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=choice["message"].get("tool_calls"),
            raw_response=data,
        )

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> AsyncIterator[ChatResponse]:
        """Stream chat completion."""
        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    if data_str:
                        import json

                        data = json.loads(data_str)
                        if data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            if delta.get("content"):
                                yield ChatResponse(
                                    content=delta["content"],
                                    model=data.get("model", payload["model"]),
                                    provider=ModelProvider.OPENROUTER,
                                    finish_reason=data["choices"][0].get("finish_reason") or "stop",
                                )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings via OpenRouter (limited support)."""
        client = self._get_client()
        response = await client.post(
            "/embeddings",
            json={
                "model": model,
                "input": texts,
            },
        )
        response.raise_for_status()
        data = response.json()

        return EmbeddingResponse(
            embeddings=[d["embedding"] for d in data["data"]],
            model=data["model"],
            provider=ModelProvider.OPENROUTER,
            usage=data.get("usage", {}),
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available OpenRouter models."""
        if self._models_cache:
            return self._models_cache

        # Skip if no valid API key
        if not self.api_key or self.api_key.startswith("${") or self.api_key == "test":
            self._models_cache = []
            return []

        try:
            client = self._get_client()
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            # Handle both array and object responses
            if isinstance(data, list):
                model_list = data
            elif isinstance(data, dict):
                model_list = data.get("data", [])
            else:
                model_list = []

            models = []
            for model_data in model_list:
                if not isinstance(model_data, dict):
                    continue
                model_id = model_data.get("id", "")
                if not model_id:
                    continue
                # Parse pricing
                pricing = model_data.get("pricing", {})
                input_price = float(pricing.get("prompt", 0)) * 1_000_000  # Convert to per 1M
                output_price = float(pricing.get("completion", 0)) * 1_000_000

                # Determine capabilities from model metadata
                capabilities = [ModelCapability.CHAT, ModelCapability.STREAMING]
                context_window = model_data.get("context_length", 4096)

                # Some models support function calling
                if model_data.get("supported_parameters", {}).get("tools"):
                    capabilities.append(ModelCapability.FUNCTION_CALLING)
                if "vision" in model_id.lower() or "multimodal" in model_id.lower():
                    capabilities.append(ModelCapability.VISION)

                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_data.get("name", model_id),
                        provider=ModelProvider.OPENROUTER,
                        capabilities=capabilities,
                        context_window=context_window,
                        max_output_tokens=model_data.get("top_provider", {}).get(
                            "max_completion_tokens", 4096
                        ),
                        pricing={"input": input_price, "output": output_price}
                        if input_price or output_price
                        else {},
                        metadata={
                            "description": model_data.get("description", ""),
                            "architecture": model_data.get("architecture", {}),
                            "top_provider": model_data.get("top_provider", {}),
                        },
                    )
                )

            self._models_cache = models
            return models
        except (httpx.HTTPError, ValueError) as e:
            print(f"Failed to fetch OpenRouter models: {e}")
            self._models_cache = []
            return []

    async def health_check(self) -> bool:
        """Check if OpenRouter API is accessible."""
        if not self.api_key or self.api_key.startswith("${") or self.api_key == "test":
            return False
        try:
            client = self._get_client()
            response = await client.get("/models", timeout=10.0)
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False


def register_openrouter(config: dict | None = None) -> OpenRouterProvider:
    """Register OpenRouter provider with registry."""
    config = config or {}
    provider = OpenRouterProvider(config)
    registry.register(provider)
    return provider
