import pytest

import app.auth as auth


@pytest.fixture(autouse=True)
def configured_credentials(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "dua")
    monkeypatch.setenv("AUTH_PASSWORD", "correct-horse")
    auth._active_tokens.clear()
    yield
    auth._active_tokens.clear()


def test_login_with_correct_credentials_issues_token():
    token = auth.login("dua", "correct-horse")
    assert token
    assert auth.is_valid(token) is True


def test_login_with_wrong_password_raises():
    with pytest.raises(auth.AuthError):
        auth.login("dua", "wrong-password")


def test_login_with_wrong_username_raises():
    with pytest.raises(auth.AuthError):
        auth.login("not-dua", "correct-horse")


def test_logout_invalidates_token():
    token = auth.login("dua", "correct-horse")
    auth.logout(token)
    assert auth.is_valid(token) is False


def test_is_valid_rejects_unknown_or_none_token():
    assert auth.is_valid(None) is False
    assert auth.is_valid("made-up-token") is False


def test_each_login_issues_a_distinct_token():
    token1 = auth.login("dua", "correct-horse")
    token2 = auth.login("dua", "correct-horse")
    assert token1 != token2
    assert auth.is_valid(token1) and auth.is_valid(token2)


async def test_require_auth_ws_accepts_valid_and_rejects_invalid():
    from fastapi import HTTPException

    token = auth.login("dua", "correct-horse")
    assert await auth.require_auth_ws(token) == token

    with pytest.raises(HTTPException):
        await auth.require_auth_ws("garbage")

    with pytest.raises(HTTPException):
        await auth.require_auth_ws(None)
