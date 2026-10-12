"""Vapi Voice Integration Webhook and Latency Engineering."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cedar_lane_ai.adapters import get_calendar_adapter, get_sheets_adapter
from cedar_lane_ai.domain import CallIntent, CallLog
from cedar_lane_ai.services.prompts import CEDAR_LANE_SYSTEM_PROMPT
from cedar_lane_ai.services.tools import GEMINI_TOOLS_SCHEMA, execute_tool

logger = logging.getLogger(__name__)

vapi_router = APIRouter(prefix="/api/vapi", tags=["vapi"])


class VapiWebhookPayload(BaseModel):
    """Payload received from Vapi server."""

    message: dict[str, Any] = Field(..., description="Vapi event payload")


@vapi_router.post("/webhook")
async def vapi_webhook(payload: VapiWebhookPayload) -> dict[str, Any]:
    """Process real-time Vapi webhook events: tool calls and end-of-call reports."""
    calendar = get_calendar_adapter()
    sheets = get_sheets_adapter()
    msg = payload.message
    event_type = msg.get("type")

    # 1. Handle Real-Time Tool Calls
    if event_type == "tool-calls":
        tool_calls = msg.get("toolCalls", [])
        results: list[dict[str, Any]] = []

        for call in tool_calls:
            call_id = call.get("id", "")
            func_data = call.get("function", {})
            func_name = func_data.get("name", "")
            func_args_raw = func_data.get("arguments", {})

            # Parse string arguments if received as JSON string
            if isinstance(func_args_raw, str):
                try:
                    args = json.loads(func_args_raw)
                except Exception:
                    args = {}
            else:
                args = func_args_raw or {}

            logger.info("Executing Vapi tool call: %s with args: %s", func_name, args)
            tool_result = execute_tool(
                tool_name=func_name,
                arguments=args,
                calendar=calendar,
                sheets=sheets,
            )

            results.append(
                {
                    "toolCallId": call_id,
                    "result": tool_result,
                }
            )

        return {"results": results}

    # 2. Handle End-Of-Call Report
    if event_type == "end-of-call-report":
        call_obj = msg.get("call", {})
        call_id = call_obj.get("id") or msg.get("callId", "")
        customer = call_obj.get("customer", {})
        caller_phone = customer.get("number") or msg.get("phoneNumber", "Unknown Phone")
        caller_name = customer.get("name") or "Phone Caller"
        summary = msg.get("summary") or "Vapi voice call completed."
        transcript = msg.get("transcript") or ""
        duration = msg.get("durationSeconds", 0)

        # Infer intent
        t_lower = transcript.lower()
        if "book" in t_lower:
            intent = CallIntent.BOOKING
        elif "reschedule" in t_lower:
            intent = CallIntent.RESCHEDULE
        elif "cancel" in t_lower:
            intent = CallIntent.CANCELLATION
        elif "late" in t_lower:
            intent = CallIntent.RUNNING_LATE
        elif "dispute" in t_lower or "bill" in t_lower or "damage" in t_lower:
            intent = CallIntent.COMPLAINT
        else:
            intent = CallIntent.INQUIRY

        # Check if follow-up required
        needs_human = (
            intent == CallIntent.COMPLAINT
            or "manager" in t_lower
            or "follow-up" in summary.lower()
        )

        contact = sheets.upsert_contact(
            phone_number=caller_phone,
            customer_name=caller_name if caller_name != "Phone Caller" else "",
            notes=f"Voice call interaction ({intent.value})",
            is_booking=(intent == CallIntent.BOOKING),
        )

        call_log = CallLog(
            call_id=call_id,
            contact_id=contact.contact_id,
            phone=caller_phone,
            caller_name=caller_name,
            started_at=datetime.now().isoformat(timespec="seconds"),
            channel="phone",
            intent=intent.value,
            outcome=f"Completed voice call ({duration}s)",
            appointment_id=None,
            handoff_required=needs_human,
            handoff_reason="Customer complaint or requested manager" if needs_human else "",
            summary=summary,
            status="completed" if not needs_human else "unresolved",
            vapi_call_id=call_id,
        )
        sheets.append_call_log(call_log)
        logger.info("Saved end-of-call report to Google Sheets for Call ID: %s", call_id)
        return {"status": "success", "logged_call_id": call_id}

    return {"status": "ignored", "event_type": event_type}


@vapi_router.get("/web-config")
async def get_vapi_web_config() -> dict[str, Any]:
    """Return public configuration required for in-browser Vapi voice calls."""
    from cedar_lane_ai.config import settings

    return {
        "publicKey": settings.vapi_public_key,
        "assistantId": settings.vapi_assistant_id,
        "hasConfig": bool(settings.vapi_public_key and settings.vapi_assistant_id),
    }


@vapi_router.get("/assistant-config")
async def get_vapi_assistant_config(server_url: str | None = None) -> dict[str, Any]:
    """Return tuned Vapi Assistant JSON blueprint adhering to <1.2s latency knobs."""
    from cedar_lane_ai.config import settings

    callback_url = server_url or settings.webhook_url or "/api/vapi/webhook"

    # Convert Gemini schema to Vapi function tool definitions
    vapi_tools = [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
            "server": {"url": callback_url},
        }
        for schema in GEMINI_TOOLS_SCHEMA
    ]

    return {
        "name": "Cedar Lane AI Receptionist",
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en",
            "endpointing": 280,  # 280ms endpointing for fast turn-taking
            "smartFormat": True,
        },
        "model": {
            "provider": "google",
            "model": "gemini-2.5-flash",
            "temperature": 0.2,
            "systemPrompt": CEDAR_LANE_SYSTEM_PROMPT,
            "tools": vapi_tools,
        },
        "voice": {
            "provider": "cartesia",
            "voiceId": "sonic-english",
            "model": "sonic-english",  # TTFB < 100ms
        },
        "silenceTimeoutSeconds": 0.5,  # Avoids dead air
        "maxDurationSeconds": 600,
        "firstMessage": (
            "Hello! Thank you for calling Cedar Lane Auto Detailing. "
            "How can I assist you with your vehicle today?"
        ),
        "fillerWords": [
            "Let me check our calendar for you...",
            "One moment while I check that slot...",
            "Looking that up right now...",
        ],
    }
