"""Tests for xcopilot.tools.delegation DelegationTool."""

from __future__ import annotations

import pytest

from xcopilot.permission.pipeline import PermissionMode, PermissionPipeline
from xcopilot.tools.delegation import DelegationTool


def test_delegation_tool_approves_leaf_standard() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.STANDARD))
    assert tool.is_approved("test goal", "leaf", ()) is True


def test_delegation_tool_denies_orchestrator_standard() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.STANDARD))
    assert tool.is_approved("test goal", "orchestrator", ()) is False


def test_delegation_tool_denies_broad_toolsets_standard() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.STANDARD))
    assert tool.is_approved("test goal", "leaf", ("shell", "file", "web")) is False


def test_delegation_tool_allows_bypass() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.BYPASS))
    assert tool.is_approved("test goal", "orchestrator", ("shell", "file", "web")) is True


def test_delegation_tool_denies_plan() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.PLAN))
    assert tool.is_approved("test goal", "leaf", ()) is False


def test_delegation_tool_allows_dont_ask() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.DONT_ASK))
    assert tool.is_approved("test goal", "orchestrator", ()) is True


def test_delegation_tool_asks_auto_ask() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.AUTO_ASK))
    assert tool.is_approved("test goal", "leaf", ()) is False


def test_delegation_tool_name() -> None:
    tool = DelegationTool(PermissionPipeline(PermissionMode.STANDARD))
    assert tool.name == "delegate_task"