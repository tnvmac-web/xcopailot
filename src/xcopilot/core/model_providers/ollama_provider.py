"""Ollama model provider implementation for local models."""

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


class OllamaProvider(ModelProviderBase):
    """Ollama local models provider."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = (
            config.get("base_url") or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        )
        self._client = None
        self._models_cache: list[ModelInfo] = []

    @property
    def provider_type(self) -> ModelProvider:
        return ModelProvider.OLLAMA

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
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
        """Chat completion via Ollama API."""
        client = self._get_client()

        # Convert messages to Ollama format
        ollama_messages = []
        for msg in messages:
            ollama_msg = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                ollama_msg["tool_calls"] = msg.tool_calls
            ollama_messages.append(ollama_msg)

        payload: dict = {
            "model": model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        if stream:
            return self._stream_chat(client, payload)

        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return ChatResponse(
            content=data["message"]["content"],
            model=data["model"],
            provider=ModelProvider.OLLAMA,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
            finish_reason="stop" if data.get("done") else "length",
            raw_response=data,
        )

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict,
    ) -> AsyncIterator[ChatResponse]:
        """Stream chat completion from Ollama."""
        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    import json

                    data = json.loads(line)
                    if "message" in data and data["message"].get("content"):
                        yield ChatResponse(
                            content=data["message"]["content"],
                            model=data["model"],
                            provider=ModelProvider.OLLAMA,
                            finish_reason="stop" if data.get("done") else "length",
                        )

    async def embeddings(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResponse:
        """Generate embeddings via Ollama API."""
        client = self._get_client()

        embeddings = []
        total_tokens = 0
        for text in texts:
            response = await client.post(
                "/api/embeddings",
                json={
                    "model": model,
                    "prompt": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data["embedding"])
            # Ollama doesn't return token counts for embeddings

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model,
            provider=ModelProvider.OLLAMA,
            usage={"total_tokens": total_tokens},
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available Ollama models (from local server)."""
        if self._models_cache:
            return self._models_cache

        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("models", []):
                model_name = model_data["name"]
                # Determine capabilities from model name
                capabilities = [ModelCapability.CHAT, ModelCapability.STREAMING]
                if "vision" in model_name.lower() or "llava" in model_name.lower():
                    capabilities.append(ModelCapability.VISION)
                if "code" in model_name.lower():
                    capabilities.append(ModelCapability.FUNCTION_CALLING)

                models.append(
                    ModelInfo(
                        id=model_name,
                        name=model_name,
                        provider=ModelProvider.OLLAMA,
                        capabilities=capabilities,
                        context_window=model_data.get("details", {}).get("context_length", 4096),
                        metadata={
                            "size": model_data.get("size", 0),
                            "digest": model_data.get("digest", ""),
                            "modified_at": model_data.get("modified_at", ""),
                        },
                    )
                )

            self._models_cache = models
            return models
        except (httpx.HTTPError, ValueError):
            # Return empty list if Ollama not running
            self._models_cache = []
            return []

    async def pull_model(self, model: str) -> AsyncIterator[dict]:
        """Pull a model from Ollama registry."""
        client = self._get_client()
        async with client.stream(
            "POST", "/api/pull", json={"name": model, "stream": True}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    import json

                    yield json.loads(line)

    async def delete_model(self, model: str) -> bool:
        """Delete a model from Ollama."""
        client = self._get_client()
        response = await client.request("DELETE", "/api/delete", json={"name": model})
        response.raise_for_status()
        # Invalidate cache
        self._models_cache = []
        return True

    async def health_check(self) -> bool:
        """Check if Ollama server is running."""
        try:
            client = self._get_client()
            response = await client.get("/api/tags", timeout=5.0)
            return response.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False


def register_ollama(config: dict | None = None) -> OllamaProvider:
    """Register Ollama provider with registry."""
    config = config or {}
    provider = OllamaProvider(config)
    registry.register(provider)
    return provider
