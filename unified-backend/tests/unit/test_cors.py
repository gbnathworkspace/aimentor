"""Unit test — CORS middleware allows the configured dev origin."""

import pytest


@pytest.mark.asyncio
async def test_preflight_allows_configured_origin(client):
    """An OPTIONS preflight from the dev origin is permitted with the right headers."""
    resp = await client.options(
        "/api/profile",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
async def test_actual_request_carries_cors_header(client, auth_headers):
    """A simple GET from the dev origin echoes the allow-origin header."""
    resp = await client.get(
        "/health", headers={"Origin": "http://localhost:5173", **auth_headers}
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
