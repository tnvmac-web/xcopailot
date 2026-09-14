"""Tests for X-Copilot server delegation API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import DEFAULT_PASSWORD, DEFAULT_USERNAME, app

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"username": DEFAULT_USERNAME, "password": DEFAULT_PASSWORD})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_delegation_delegate() -> None:
    headers = _auth_headers()
    resp = client.post(
        "/api/delegation/delegate",
        json={"goal": "test delegation"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"


def test_delegation_delegate_missing_goal() -> None:
    headers = _auth_headers()
    resp = client.post(
        "/api/delegation/delegate",
        json={},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "goal is required" in resp.json()["detail"]


def test_delegation_status_not_found() -> None:
    headers = _auth_headers()
    resp = client.get(
        "/api/delegation/status/nonexistent",
        headers=headers,
    )
    assert resp.status_code == 404


def test_delegation_list_empty() -> None:
    headers = _auth_headers()
    resp = client.get("/api/delegation/tasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert isinstance(data["tasks"], list)


def test_delegation_summary() -> None:
    headers = _auth_headers()
    resp = client.get("/api/delegation/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tasks" in data
    assert "by_status" in data


def test_delegation_history() -> None:
    headers = _auth_headers()
    resp = client.get("/api/delegation/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "history" in data
    assert isinstance(data["history"], list)