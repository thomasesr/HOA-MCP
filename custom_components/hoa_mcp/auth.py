"""Odysseus auth helpers — login via session cookie, create API token."""

import logging

import aiohttp

logger = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Raised when Odysseus is unreachable or returns an unexpected error."""


class InvalidAuth(Exception):
    """Raised when credentials are rejected (401/403)."""


async def obtain_token(url: str, username: str, password: str) -> str:
    """Log in to Odysseus with username/password and create an API token.

    Returns the raw token string (ody_xxx). Never persists credentials.
    Raises CannotConnect on network errors, InvalidAuth on 401/403.
    """
    base = url.rstrip("/")
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1 — login, capture session cookie
            login_resp = await session.post(
                f"{base}/api/auth/login",
                json={"username": username, "password": password},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if login_resp.status in (401, 403):
                raise InvalidAuth("Invalid username or password")
            if login_resp.status != 200:
                raise CannotConnect(f"Login failed with status {login_resp.status}")

            # Step 2 — create token using the session cookie aiohttp already holds
            token_resp = await session.post(
                f"{base}/api/tokens",
                data={"name": "hoa-mcp", "profile": "chat"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            if token_resp.status in (401, 403):
                raise InvalidAuth("Login succeeded but token creation was denied — ensure the account has admin rights")
            if token_resp.status != 200:
                raise CannotConnect(f"Token creation failed with status {token_resp.status}")

            body = await token_resp.json()
            token = body.get("token", "")
            if not token:
                raise CannotConnect("Token creation response missing token field")

            return token

    except (InvalidAuth, CannotConnect):
        raise
    except aiohttp.ClientError as exc:
        raise CannotConnect(str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error during Odysseus token creation")
        raise CannotConnect(str(exc)) from exc
