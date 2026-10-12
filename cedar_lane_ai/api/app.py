"""FastAPI application serving AI Receptionist API and Phase 1 Web UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cedar_lane_ai.adapters import (
    InMemoryCalendarAdapter,
    InMemorySheetsAdapter,
    get_calendar_adapter,
    get_sheets_adapter,
)
from cedar_lane_ai.api.vapi import vapi_router
from cedar_lane_ai.domain import ServiceType
from cedar_lane_ai.services import ReceptionistAgent

app = FastAPI(
    title="Cedar Lane Auto Detailing — AI Receptionist",
    description="Autonomous AI Receptionist with two-way Calendar and Sheets synchronization",
    version="0.1.0",
)

app.include_router(vapi_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

calendar_adapter = get_calendar_adapter()
sheets_adapter = get_sheets_adapter()
agent = ReceptionistAgent(calendar=calendar_adapter, sheets=sheets_adapter)


class ActionItem(BaseModel):
    """Normalized tool action item."""

    tool: str
    input: Any = None
    result: Any = None


class ChatRequest(BaseModel):
    """Payload for conversational turn."""

    message: str = Field(..., description="Caller's text message")
    session_id: str | None = Field(default=None, description="Optional conversation session ID")
    phone: str = Field(default="+1 (555) 234-5678", description="Caller phone number")
    history: list[dict[str, Any]] = Field(default_factory=list, description="Prior turn history")


class ChatResponse(BaseModel):
    """Response containing assistant text and executed tool events."""

    reply: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)


session_histories: dict[str, list[dict[str, Any]]] = {}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    """Process incoming caller message and return agent response with tool events."""
    augmented_message = payload.message
    # If caller phone is specified and not in message, append it contextually
    if payload.phone and payload.phone not in augmented_message:
        augmented_message = f"{payload.message} (My phone number is {payload.phone})"

    # Retrieve prior history from session_id or explicit payload history
    prior_history = payload.history
    if not prior_history and payload.session_id:
        prior_history = session_histories.get(payload.session_id, [])

    reply, updated_history, tool_events = agent.process_turn(
        user_message=augmented_message,
        conversation_history=prior_history,
    )

    if payload.session_id:
        session_histories[payload.session_id] = updated_history

    actions = [
        ActionItem(
            tool=ev.get("tool_name", ""),
            input=ev.get("arguments"),
            result=ev.get("result"),
        )
        for ev in tool_events
    ]

    return ChatResponse(
        reply=reply,
        history=updated_history,
        tool_events=tool_events,
        actions=actions,
    )


@app.get("/api/state")
async def get_state(date: str = "2026-10-15") -> dict[str, Any]:
    """Retrieve live snapshot of calendar appointments, contacts, and call logs."""
    appointments = calendar_adapter.list_day_events(date)
    contacts = sheets_adapter.list_contacts()
    logs = sheets_adapter.list_call_logs(limit=50)

    return {
        "date": date,
        "appointments": [apt.model_dump(mode="json") for apt in appointments],
        "contacts": [c.model_dump(mode="json") for c in contacts],
        "call_logs": [log.model_dump(mode="json") for log in logs],
    }


@app.post("/api/seed-demo")
async def seed_demo_scenario() -> dict[str, Any]:
    """Seed the specific Thursday 3:30 PM conflict demo scenario."""
    test_date = "2026-10-15"  # Thursday

    if isinstance(calendar_adapter, InMemoryCalendarAdapter):
        calendar_adapter.clear()
    if isinstance(sheets_adapter, InMemorySheetsAdapter):
        sheets_adapter.clear()

    # Seed pre-booked appointment at 3:30 PM (90 mins Interior Detail)
    calendar_adapter.create_appointment_event(
        customer_name="David Miller",
        phone="+1 (555) 888-9999",
        service=ServiceType.INTERIOR_DETAIL,
        vehicle_type="SUV",
        start_dt=datetime(2026, 10, 15, 15, 30),
        end_dt=datetime(2026, 10, 15, 17, 0),
        notes="Pre-booked appointment for demo collision testing.",
    )

    sheets_adapter.upsert_contact(
        phone_number="+1 (555) 888-9999",
        customer_name="David Miller",
        vehicle_type="SUV",
        notes="Pre-booked client",
        is_booking=True,
    )

    return {
        "status": "success",
        "message": (
            "Seeded demo scenario: Thursday 2026-10-15 has an existing 3:30 PM - 5:00 PM "
            "Interior Detail for David Miller. Next booking request for 3:30 PM will conflict "
            "and suggest alternative slots (e.g. 2:00 PM or 5:00 PM Express)."
        ),
        "target_date": test_date,
    }


@app.post("/api/reset")
async def reset_state() -> dict[str, str]:
    """Reset in-memory data stores."""
    if isinstance(calendar_adapter, InMemoryCalendarAdapter):
        calendar_adapter.clear()
    if isinstance(sheets_adapter, InMemorySheetsAdapter):
        sheets_adapter.clear()
    return {"status": "success", "message": "Demo data reset successfully."}


# Mount static directory for frontend
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
