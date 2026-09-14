"""Conversation loop — prompt processing, tool execution, response generation.

Mirrors X-Copilot agent loop pattern:
- Input → prompt builder → provider API → tool dispatch → response
- Tool registry for dynamic tool discovery and dispatch
- State layer for session persistence
- Config system for settings
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from xcopilot.config import load_config
from xcopilot.core.delegation import TaskDelegator
from xcopilot.core.models import ChatMessage, ChatResponse, registry
from xcopilot.permission.pipeline import PermissionAction, PermissionPipeline, PermissionMode
from xcopilot.state.db import StateDB
from xcopilot.tools.registry import ToolRegistry


class ConversationLoop:
    """Lightweight agent loop used by the local API and CLI entrypoints.

    Uses the tool registry for dynamic tool discovery and dispatch,
    the state layer for session persistence, and the config system
    for settings.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        state_db: StateDB | None = None,
    ) -> None:
        self._tools = tool_registry or ToolRegistry()
        self._state = state_db or StateDB()
        self._sessions: dict[str, list[ChatMessage]] = {}
        self._config = load_config()

    # ── Session management ─────────────────────────────────

    def get_session_state(self, session_id: str) -> list[ChatMessage]:
        """Return the current message history for a session."""
        return list(self._sessions.get(session_id, []))

    def save_session(self, session_id: str) -> None:
        """Persist session to the state layer."""
        messages = self._sessions.get(session_id, [])
        session = self._state.get_session(session_id)
        if session is None:
            session = self._state.create_session(
                profile=self._config.get("profile", "default"),
                title=f"Session {session_id[:8]}",
            )
        for msg in messages:
            msg_record = {
                "id": msg.content[:20] + "...",  # simplified ID
                "session_id": session_id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp if hasattr(msg, "timestamp") else "",
            }
        self._state.update_session(session_id, updated_at=msg_record["timestamp"] if msg_record else "")

    # ── Prompt processing ──────────────────────────────────

    async def process_prompt(
        self,
        session_id: str,
        messages: list[ChatMessage],
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        context_mode: str = "auto",
        stream: bool = False,
    ) -> ChatResponse | AsyncIterator[ChatResponse]:
        """Process a user prompt and return an assistant response."""
        if not messages:
            raise ValueError("At least one message is required")

        history = self._sessions.setdefault(session_id, [])
        history.extend(messages)
        request_messages = messages
        if context_mode == "auto":
            request_messages, max_tokens = await self._fit_context(
                messages, model, max_tokens
            )

        try:
            response = await registry.chat_with_fallback(
                request_messages,
                model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            raise RuntimeError(
                f"No configured model provider could serve '{model}'. "
                f"{type(exc).__name__}: {exc}. "
                "Check the provider key, model ID, and backend connectivity."
            ) from exc

        # Save tool calls from response to session
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                await self.handle_tool_call(tc.get("name", ""), tc.get("arguments", {}))

        # Save to state layer
        self.save_session(session_id)

        return response

    async def _fit_context(
        self,
        messages: list[ChatMessage],
        model: str,
        max_tokens: int | None,
    ) -> tuple[list[ChatMessage], int | None]:
        """Fit cloud requests to the selected model context window."""
        model_info = None
        for provider_models in (await registry.list_all_models()).values():
            model_info = next((item for item in provider_models if item.id == model), None)
            if model_info:
                break
        if not model_info or not model_info.context_window:
            return messages, max_tokens

        output_tokens = min(
            max_tokens or model_info.max_output_tokens, model_info.max_output_tokens
        )
        input_budget = max(model_info.context_window - output_tokens, 256)
        estimated_tokens = sum(max(1, len(message.content) // 4) for message in messages)
        if estimated_tokens <= input_budget:
            return messages, output_tokens

        system_messages = [message for message in messages if message.role == "system"]
        remaining = input_budget - sum(
            max(1, len(message.content) // 4) for message in system_messages
        )
        selected: list[ChatMessage] = []
        for message in reversed(
            [item for item in messages if message.role != "system"]
        ):
            message_tokens = max(1, len(message.content) // 4)
            if message_tokens > remaining:
                break
            selected.append(message)
            remaining -= message_tokens
        selected.reverse()
        return system_messages + selected, output_tokens

    # ── Tool dispatch ──────────────────────────────────────

    async def handle_tool_call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Handle a tool call request from the model.

        Dispatches through the tool registry if the tool is registered,
        otherwise falls back to built-in handlers (delegate_task).
        """
        # Check if tool is registered
        spec = self._tools.get(tool_name)
        if spec is not None:
            try:
                tool = spec.factory(pipeline=self._get_pipeline())
                result = tool.execute(**args)
                return {
                    "tool": tool_name,
                    "args": args,
                    "status": "completed" if result.success else "error",
                    "result": result.output,
                    "data": result.data,
                }
            except Exception as exc:
                return {
                    "tool": tool_name,
                    "args": args,
                    "status": "error",
                    "result": str(exc),
                }

        # Built-in handlers
        if tool_name == "delegate_task":
            return await self._handle_delegation(args)

        return {
            "tool": tool_name,
            "args": args,
            "status": "not_implemented",
            "result": f"Tool '{tool_name}' is not available for this model runtime.",
        }

    def _get_pipeline(self) -> PermissionPipeline:
        """Get the permission pipeline from config."""
        mode_str = self._config.get("permission_mode", "standard")
        try:
            mode = PermissionMode(mode_str.lower())
        except ValueError:
            mode = PermissionMode.STANDARD
        return PermissionPipeline(mode)

    async def _handle_delegation(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle a delegate_task tool call from the model."""
        goal = args.get("goal", "")
        if not goal:
            return {
                "tool": "delegate_task",
                "args": args,
                "status": "error",
                "result": "goal is required",
            }

        context = args.get("context")
        role = args.get("role", "leaf")
        model = args.get("model")
        toolsets = args.get("allowed_toolsets")
        permission_mode = args.get("permission_mode", "standard")
        metadata = args.get("metadata", {})

        try:
            mode = PermissionMode(permission_mode.lower())
        except ValueError:
            mode = PermissionMode.STANDARD

        pipeline = PermissionPipeline(mode)
        delegator = TaskDelegator()

        # Permission check
        if not delegator._pipeline.check(PermissionAction.DELEGATE, {"goal": goal}):
            return {
                "tool": "delegate_task",
                "args": args,
                "status": "denied",
                "result": "Permission denied by pipeline",
            }

        task = delegator.delegate(
            goal, context=context, role=role, model=model,
            allowed_toolsets=tuple(toolsets or []), metadata=metadata,
        )

        try:
            result = await delegator.run(task.task_id)
            return {
                "tool": "delegate_task",
                "args": args,
                "status": "completed",
                "result": result.status.value,
                "task_id": result.task_id,
                "summary": result.summary,
                "error": result.error,
                "duration_seconds": result.duration_seconds,
                "api_calls": result.api_calls,
            }
        except Exception as exc:
            return {
                "tool": "delegate_task",
                "args": args,
                "status": "error",
                "result": str(exc),
                "task_id": task.task_id,
            }

    # ── Clarification & approval ───────────────────────────

    async def handle_clarification(
        self, question: str, choices: list[str] | None = None
    ) -> str:
        """Return a safe clarification response."""
        if choices:
            return choices[0]
        return question

    async def handle_approval(self, command: str) -> bool:
        """Default approvals require explicit user confirmation outside the runtime."""
        return command.strip() == ""