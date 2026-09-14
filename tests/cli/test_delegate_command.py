"""Tests for xcopilot CLI delegation commands."""

from __future__ import annotations

import pytest

from click.testing import CliRunner

from xcopilot.cli.main import cli


def test_delegate_run_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "run", "--help"])
    assert result.exit_code == 0
    assert "Delegate a task" in result.output


def test_delegate_batch_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "batch", "--help"])
    assert result.exit_code == 0
    assert "Delegate multiple goals" in result.output


def test_delegate_status_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "status", "--help"])
    assert result.exit_code == 0
    assert "Check the status" in result.output


def test_delegate_list_empty() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "list"])
    assert result.exit_code == 0
    assert "No delegated tasks" in result.output


def test_delegate_cancel_missing() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "cancel", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_delegate_summary_empty() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["delegate", "summary"])
    assert result.exit_code == 0
    assert "Total tasks: 0" in result.output