"""Unit and integration tests for FastAPI application and endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from cedar_lane_ai.api.app import app


@pytest.mark.asyncio
async def test_api_state_and_seed_demo() -> None:
    """Verify /api/state and /api/seed-demo endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Reset state
        res_reset = await client.post("/api/reset")
        assert res_reset.status_code == 200

        # 2. Seed demo
        res_seed = await client.post("/api/seed-demo")
        assert res_seed.status_code == 200
        seed_data = res_seed.json()
        assert seed_data["status"] == "success"
        assert seed_data["target_date"] == "2026-10-15"

        # 3. Check state for seeded date
        res_state = await client.get("/api/state?date=2026-10-15")
        assert res_state.status_code == 200
        state_data = res_state.json()
        assert len(state_data["appointments"]) == 1
        assert state_data["appointments"][0]["customer_name"] == "David Miller"
        assert len(state_data["contacts"]) == 1


@pytest.mark.asyncio
async def test_api_chat_flow() -> None:
    """Verify conversational turn through /api/chat."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "message": "What are your shop hours and pricing for an Express Wash?",
            "phone": "+1 (555) 234-5678",
            "history": [],
        }
        res = await client.post("/api/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert len(data["history"]) >= 2
        assert "8:00 AM" in data["reply"] or "Cedar Lane" in data["reply"]


@pytest.mark.asyncio
async def test_static_html_served() -> None:
    """Verify index.html is served on root path."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        assert "Cedar Lane Auto Detailing" in res.text
