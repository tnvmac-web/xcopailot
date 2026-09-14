"""Shell tool — execute commands safely with permission checks."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from xcopilot.permission.pipeline import PermissionAction, PermissionPipeline
from xcopilot.tools.tool_base import ToolResult


class ShellTool:
    """Execute shell commands with permission checks."""

    name = "shell"
    description = "Execute shell commands with timeout and permission checks"
    toolset = "terminal"
    requires_approval = True
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "Command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["cmd"],
    }

    def __init__(self, pipeline: PermissionPipeline, timeout: int = 30) -> None:
        self.pipeline = pipeline
        self.default_timeout = timeout

    def execute(self, cmd: str, timeout: int = 30, cwd: str | None = None) -> ToolResult:
        """Execute a shell command."""
        start = time.time()
        decision = self.pipeline.check(PermissionAction.SHELL, {"cmd": cmd})
        if not decision.approved:
            return ToolResult(
                success=False,
                error=f"Shell command denied: {decision.reason}",
                duration_seconds=round(time.time() - start, 2),
            )

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            duration = time.time() - start
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    output=result.stdout,
                    duration_seconds=round(duration, 2),
                    data={"returncode": result.returncode},
                )
            return ToolResult(
                success=False,
                output=result.stdout,
                error=result.stderr,
                duration_seconds=round(duration, 2),
                data={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout}s",
                duration_seconds=round(time.time() - start, 2),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                duration_seconds=round(time.time() - start, 2),
            )


# Factory function for registry — creates instance with runtime dependencies
def shell_tool_factory(**deps: Any) -> ShellTool:
    """Factory to create ShellTool with its dependencies."""
    return ShellTool(pipeline=deps["pipeline"], timeout=deps.get("timeout", 30))