"""Single-user token auth - this is a personal QA dashboard, not a
multi-tenant product, so there's one username/password pair (env-configured)
rather than a user table. Login exchanges those credentials for an opaque
bearer token; every protected route (REST via a dependency, WebSocket via a
query param, since the browser WebSocket API can't set custom headers)
checks the token against the in-memory set of ones issued since the process
started - a restart logs everyone out, which is fine for a demo app and
avoids needing a persisted session store for something this small.
"""

import os
import secrets

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_active_tokens: set[str] = set()

_bearer_scheme = HTTPBearer(auto_error=False)


def _configured_username() -> str:
    return os.environ.get("AUTH_USERNAME", "admin")


def _configured_password() -> str:
    return os.environ.get("AUTH_PASSWORD", "admin")


class AuthError(Exception):
    """Raised for a wrong username/password at login."""


def login(username: str, password: str) -> str:
    if not (secrets.compare_digest(username, _configured_username()) and secrets.compare_digest(
        password, _configured_password()
    )):
        raise AuthError("Incorrect username or password.")
    token = secrets.token_urlsafe(32)
    _active_tokens.add(token)
    return token


def logout(token: str) -> None:
    _active_tokens.discard(token)


def is_valid(token: str | None) -> bool:
    return token is not None and token in _active_tokens


async def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> str:
    """FastAPI dependency for REST routes - reads the token from the
    Authorization: Bearer header."""
    if credentials is None or not is_valid(credentials.credentials):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return credentials.credentials


async def require_auth_ws(token: str | None = Query(default=None)) -> str:
    """WebSocket routes take the token as a query param instead - the
    browser WebSocket API has no way to set an Authorization header."""
    if not is_valid(token):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return token
