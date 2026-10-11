"""Unit tests for Phase 2 Vapi voice assistant configuration and provisioning."""

import pytest
from httpx import ASGITransport, AsyncClient

from cedar_lane_ai.api.app import app
from scripts.setup_vapi import build_assistant_payload


@pytest.mark.asyncio
async def test_vapi_web_config_endpoint() -> None:
    """Verify web-config endpoint returns public key and assistant ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/vapi/web-config")
        assert res.status_code == 200
        data = res.json()
        assert "publicKey" in data
        assert "assistantId" in data
        assert "hasConfig" in data


@pytest.mark.asyncio
async def test_vapi_assistant_config_with_custom_server_url() -> None:
    """Verify assistant config sets tool server URLs when custom URL is passed."""
    transport = ASGITransport(app=app)
    test_url = "https://custom-tunnel.ngrok-free.app/api/vapi/webhook"
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/vapi/assistant-config?server_url={test_url}")
        assert res.status_code == 200
        data = res.json()
        for tool in data["model"]["tools"]:
            assert tool["server"]["url"] == test_url


def test_build_assistant_payload_structure() -> None:
    """Verify setup_vapi script produces conforming latency knobs and tools."""
    url = "https://my-tunnel.ngrok.app/api/vapi/webhook"
    payload = build_assistant_payload(url)

    # Sub-1.2s knobs
    assert payload["transcriber"]["provider"] == "deepgram"
    assert payload["transcriber"]["model"] == "nova-2"
    assert payload["transcriber"]["endpointing"] == 280
    assert payload["voice"]["provider"] == "cartesia"
    assert payload["voice"]["model"] == "sonic-english"
    assert payload["silenceTimeoutSeconds"] == 0.5
    assert payload["serverUrl"] == url
    assert len(payload["model"]["tools"]) == 6
