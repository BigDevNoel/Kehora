"""Minimal Clerk Backend API client (only what JIT provisioning needs)."""

from typing import Any

import httpx

from kehora_common.settings import Settings, require


async def fetch_user(
    http: httpx.AsyncClient, settings: Settings, clerk_user_id: str
) -> dict[str, Any]:
    secret = require(settings.clerk_secret_key, "CLERK_SECRET_KEY").get_secret_value()
    resp = await http.get(
        f"{settings.clerk_api_url}/users/{clerk_user_id}",
        headers={"Authorization": f"Bearer {secret}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    return data
