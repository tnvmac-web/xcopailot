"""Delegation tool — permission-aware task delegation to X-Copilot subagents."""

from __future__ import annotations

from typing import Any

from xcopilot.permission.pipeline import PermissionMode, PermissionPipeline
from xcopilot.tools.tool_base import ToolResult


class DelegationTool:
    """Permission-aware task delegation tool.

    Checks the PermissionPipeline before allowing delegation:
    - leaf role + STANDARD mode → approved
    - orchestrator role → ask
    - broad toolsets → deny
    - PLAN mode → deny
    - BYPASS mode → allow
    - DONT_ASK → allow non-destructive
    - AUTO_ASK → always ask
    """

    name = "delegate_task"
    description = "Delegate a task to an X-Copilot subagent (permission-aware)"
    toolset = "delegation"
    requires_approval = True
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Task goal"},
            "context": {"type": "string", "description": "Context for the subagent"},
            "role": {"type": "string", "enum": ["leaf", "orchestrator"], "default": "leaf"},
            "model": {"type": "string", "description": "Model override"},
            "toolsets": {"type": "array", "items": {"type": "string"}, "description": "Allowed toolsets"},
            "mode": {"type": "string", "enum": ["standard", "auto-ask", "plan", "bypass", "dont-ask"], "default": "standard"},
            "background": {"type": "boolean", "description": "Run in background"},
        },
        "required": ["goal"],
    }

    def __init__(self, pipeline: PermissionPipeline) -> None:
        self.pipeline = pipeline

    def is_approved(self, goal: str, role: str, toolsets: tuple[str, ...]) -> bool:
        """Check if delegation is approved by the permission pipeline."""
        mode = self.pipeline.mode
        if mode == PermissionMode.BYPASS:
            return True
        if mode == PermissionMode.PLAN:
            return False
        if mode == PermissionMode.DONT_ASK:
            return True
        if mode == PermissionMode.AUTO_ASK:
            return False
        # STANDARD mode
        if role == "orchestrator":
            return False
        if len(toolsets) > 2:
            return False
        return True

    def execute(
        self,
        goal: str,
        context: str | None = None,
        role: str = "leaf",
        model: str | None = None,
        toolsets: list[str] | None = None,
        mode: str = "standard",
        background: bool = False,
    ) -> ToolResult:
        """Execute delegation with permission check."""
        from xcopilot.core.delegation import TaskDelegator
        from xcopilot.permission.pipeline import PermissionMode as PM

        toolsets_tuple = tuple(toolsets or ())
        if not self.is_approved(goal, role, toolsets_tuple):
            return ToolResult(
                success=False,
                error="Delegation not approved by permission pipeline",
            )

        perm_mode = PM(mode)
        delegator = TaskDelegator(
            project_root=".",
            permission_mode=perm_mode,
            parent_session_id=None,
        )
        task = delegator.delegate(
            goal, context=context, role=role, model=model,
            allowed_toolsets=toolsets_tuple,
        )
        return ToolResult(
            success=True,
            output=f"Delegated task {task.task_id}: {goal[:60]}",
            data={"task_id": task.task_id, "status": task.status.value},
        )


def delegation_tool_factory(**deps: Any) -> DelegationTool:
    """Factory to create DelegationTool with its dependencies."""
    return DelegationTool(pipeline=deps["pipeline"])