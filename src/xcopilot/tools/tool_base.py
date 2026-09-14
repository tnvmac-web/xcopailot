"""Base class for all X-Copilot tools.

Every tool inherits from BaseTool and registers itself at import time.
The registry handles schema collection, dispatch, availability checking,
and error wrapping — matching X-Copilot tools/registry.py pattern.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standard result from any tool execution."""

    success: bool
    output: str | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data,
            "duration_seconds": self.duration_seconds,
        }

    def __str__(self) -> str:
        if self.success:
            return self.output or "OK"
        return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract base class for all X-Copilot tools.

    Subclasses must define:
    - name: unique tool identifier
    - description: human-readable purpose
    - toolset: grouping category
    - schema: JSON Schema for the tool's parameters

    The tool is automatically registered in the global registry
    when the module is imported (via _tool_specs module-level list).
    """

    name: str = ""
    description: str = ""
    toolset: str = "default"
    schema: dict[str, Any] = {}
    service_gated: bool = False
    check_fn: Callable[[], bool] | None = None  # type: ignore[name-defined]
    requires_approval: bool = True

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments."""

    def _spec(self) -> dict[str, Any]:
        """Return the ToolSpec dict for registry registration."""
        from xcopilot.tools.registry import ToolSpec, registry

        spec = ToolSpec(
            name=self.name,
            description=self.description,
            toolset=self.toolset,
            schema=self.schema,
            callable=self.execute,
            service_gated=self.service_gated,
            check_fn=self.check_fn,
            requires_approval=self.requires_approval,
        )
        return spec

    def register(self) -> None:
        """Register this tool in the global registry."""
        from xcopilot.tools.registry import registry

        registry.register(self._spec())


# Module-level list for auto-discovery — each tool file appends its specs here
_tool_specs: list[Any] = []


def _auto_register(tool_instance: BaseTool) -> None:
    """Register a tool instance at module import time."""
    from xcopilot.tools.registry import registry

    registry.register(tool_instance._spec())
    _tool_specs.append(tool_instance._spec())