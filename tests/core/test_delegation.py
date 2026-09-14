"""Tests for xcopilot.core.delegation TaskDelegator."""

from __future__ import annotations

import pytest

from xcopilot.core.delegation import DelegationResult, DelegationTask, TaskDelegator, TaskStatus


def test_delegate_creates_task() -> None:
    d = TaskDelegator()
    task = d.delegate("test goal")
    assert task.task_id
    assert task.goal == "test goal"
    assert task.status == TaskStatus.PENDING
    assert task.role == "leaf"


def test_delegate_with_options() -> None:
    d = TaskDelegator()
    task = d.delegate(
        "complex goal",
        context="some context",
        role="orchestrator",
        model="gpt-4o",
        allowed_toolsets=("shell", "file"),
    )
    assert task.context == "some context"
    assert task.role == "orchestrator"
    assert task.model == "gpt-4o"
    assert task.allowed_toolsets == ("shell", "file")


def test_list_tasks() -> None:
    d = TaskDelegator()
    d.delegate("task 1")
    d.delegate("task 2")
    tasks = d.list_tasks()
    assert len(tasks) == 2


def test_list_tasks_filtered() -> None:
    d = TaskDelegator()
    d.delegate("task 1")
    d.delegate("task 2")
    pending = d.list_tasks(TaskStatus.PENDING)
    assert len(pending) == 2


def test_status() -> None:
    d = TaskDelegator()
    task = d.delegate("test")
    found = d.status(task.task_id)
    assert found is not None
    assert found.task_id == task.task_id


def test_status_missing() -> None:
    d = TaskDelegator()
    assert d.status("nonexistent") is None


def test_cancel_pending() -> None:
    d = TaskDelegator()
    task = d.delegate("test")
    assert d.cancel(task.task_id) is True
    updated = d.status(task.task_id)
    assert updated is not None
    assert updated.status == TaskStatus.CANCELLED


def test_cancel_missing() -> None:
    d = TaskDelegator()
    assert d.cancel("nonexistent") is False


def test_summary() -> None:
    d = TaskDelegator()
    d.delegate("task 1")
    d.delegate("task 2")
    s = d.summary()
    assert s["total_tasks"] == 2
    assert "pending" in s["by_status"]
    assert s["by_status"]["pending"] == 2


def test_delegation_task_frozen() -> None:
    """DelegationTask is frozen — attributes immutable."""
    from xcopilot.permission.pipeline import PermissionMode

    task = DelegationTask(
        task_id="abc",
        goal="test",
        context=None,
        role="leaf",
        model=None,
        allowed_toolsets=(),
        permission_mode=PermissionMode.STANDARD,
        parent_session_id=None,
    )
    with pytest.raises(Exception):
        task.goal = "changed"  # type: ignore[misc]


def test_delegation_result_dataclass() -> None:
    r = DelegationResult(
        task_id="abc", status=TaskStatus.SUCCEEDED, summary="done", error=None, duration_seconds=1.5,
    )
    assert r.task_id == "abc"
    assert r.status == TaskStatus.SUCCEEDED
    assert r.duration_seconds == 1.5