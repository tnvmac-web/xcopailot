"""LM Studio model provider implementation for local models."""

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


class LMStudioProvider(ModelProviderBase):
    """LM Studio local models provider (OpenAI-compatible API)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = (
            config.get("base_url")
            or os.environ.get("LMSTUDIO_BASE_URL")
            or "http://localhost:1234/v1"
        )
        self.api_key = config.get("api_key") or "lm-studio"  # LM Studio accepts any key
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.LMSTUDIO

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
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
        """Chat completion via LM Studio (OpenAI-compatible) API."""
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
            provider=ModelProvider.LMSTUDIO,
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
                                    provider=ModelProvider.LMSTUDIO,
                                    finish_reason=data["choices"][0].get("finish_reason") or "stop",
                                )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings via LM Studio API."""
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
            provider=ModelProvider.LMSTUDIO,
            usage=data.get("usage", {}),
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available LM Studio models."""
        if self._models_cache:
            return self._models_cache

        try:
            client = self._get_client()
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                model_id = model_data["id"]
                # LM Studio models are typically loaded GGUF files
                capabilities = [ModelCapability.CHAT, ModelCapability.STREAMING]
                if "vision" in model_id.lower() or "llava" in model_id.lower():
                    capabilities.append(ModelCapability.VISION)

                models.append(
                    ModelInfo(
                        id=model_id,
                        name=model_id,
                        provider=ModelProvider.LMSTUDIO,
                        capabilities=capabilities,
                        context_window=model_data.get("context_length", 4096),
                        metadata={
                            "owned_by": model_data.get("owned_by", "lm-studio"),
                        },
                    )
                )

            self._models_cache = models
            return models
        except (httpx.HTTPError, ValueError):
            self._models_cache = []
            return []

    async def health_check(self) -> bool:
        """Check if LM Studio server is running."""
        try:
            client = self._get_client()
            response = await client.get("/models", timeout=5.0)
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False


def register_lmstudio(config: dict | None = None) -> LMStudioProvider:
    """Register LM Studio provider with registry."""
    config = config or {}
    provider = LMStudioProvider(config)
    registry.register(provider)
    return provider
