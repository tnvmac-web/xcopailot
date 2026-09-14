"""Shared auth dependency and token store for X-Copilot server.

Breaks circular import between server.main and server.web_routers.
Both modules import from this shared auth module.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, status as http_status

# Persistent in-memory session state for authenticated clients
ACTIVE_TOKENS: dict[str, str] = {}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[_hash_token(token)] = username
    return token


def _validate_token(token: str | None) -> str:
    if not token:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    username = ACTIVE_TOKENS.get(_hash_token(token))
    if not username:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return username


def require_auth(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Bearer token auth dependency — validates against ACTIVE_TOKENS."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    return _validate_token(token)