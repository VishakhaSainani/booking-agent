"""Unit and integration tests for Vapi Voice Webhook and assistant config."""

import pytest
from httpx import ASGITransport, AsyncClient

from cedar_lane_ai.adapters import InMemorySheetsAdapter, get_sheets_adapter
from cedar_lane_ai.api.app import app


@pytest.mark.asyncio
async def test_vapi_tool_calls_webhook() -> None:
    """Verify Vapi tool-calls webhook execution returns expected results payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "message": {
                "type": "tool-calls",
                "toolCalls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "check_availability",
                            "arguments": {
                                "date": "2026-10-15",
                                "time": "10:00 AM",
                                "service_type": "Express Wash & Vac",
                            },
                        },
                    }
                ],
            }
        }
        res = await client.post("/api/vapi/webhook", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["toolCallId"] == "call_abc123"
        assert data["results"][0]["result"]["available"] is True


@pytest.mark.asyncio
async def test_vapi_end_of_call_report() -> None:
    """Verify end-of-call report saves metadata to Google Sheets Call Logs."""
    transport = ASGITransport(app=app)
    sheets = get_sheets_adapter()
    if isinstance(sheets, InMemorySheetsAdapter):
        sheets.clear()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {
                    "id": "vapi_call_9999",
                    "customer": {
                        "number": "+15559876543",
                        "name": "Sarah Connor",
                    },
                },
                "transcript": "Caller: Can I book an Express Wash for tomorrow? Agent: Confirmed!",
                "summary": "Customer successfully booked an appointment.",
                "durationSeconds": 135,
            }
        }
        res = await client.post("/api/vapi/webhook", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["logged_call_id"] == "vapi_call_9999"

        # Verify sheets contains the log
        logs = sheets.list_call_logs(limit=10)
        assert len(logs) >= 1
        match = next((item for item in logs if item.vapi_call_id == "vapi_call_9999"), None)
        assert match is not None
        assert match.caller_name == "Sarah Connor"
        assert match.caller_phone == "+15559876543"


@pytest.mark.asyncio
async def test_vapi_assistant_config_latency_knobs() -> None:
    """Verify tuned assistant configuration has sub-1.2s latency properties."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/vapi/assistant-config")
        assert res.status_code == 200
        config = res.json()

        # Check sub-1.2s knobs
        assert config["transcriber"]["provider"] == "deepgram"
        assert config["transcriber"]["model"] == "nova-2"
        assert config["transcriber"]["endpointing"] == 280
        assert config["voice"]["provider"] == "cartesia"
        assert config["silenceTimeoutSeconds"] == 0.5
        assert len(config["model"]["tools"]) == 6
