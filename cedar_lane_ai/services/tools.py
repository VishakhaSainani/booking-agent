"""Deterministic shop tools and execution handlers for Cedar Lane AI Receptionist."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from cedar_lane_ai.adapters.calendar_base import CalendarAdapter
from cedar_lane_ai.adapters.in_memory_calendar import (
    parse_date_string,
    parse_time_string,
)
from cedar_lane_ai.adapters.sheets_base import SheetsAdapter
from cedar_lane_ai.domain import (
    PREPARATION_GUIDELINES,
    CallIntent,
    CallLog,
    EscalationReason,
    ServiceType,
    is_oversized_vehicle,
)

logger = logging.getLogger(__name__)


def parse_service_type(service_name: str) -> ServiceType:
    """Match string to closest ServiceType enum."""
    normalized = service_name.strip().lower()
    if "express" in normalized or "wash" in normalized:
        return ServiceType.EXPRESS_WASH
    if "interior" in normalized:
        return ServiceType.INTERIOR_DETAIL
    if "full" in normalized:
        return ServiceType.FULL_DETAIL
    if "ceramic" in normalized or "paint" in normalized or "coating" in normalized:
        return ServiceType.CERAMIC_COATING
    # Default to Express Wash if ambiguous
    return ServiceType.EXPRESS_WASH


# ==============================================================================
# Tool Execution Handlers
# ==============================================================================


def check_availability(
    calendar: CalendarAdapter,
    date: str,
    time: str,
    service_type: str,
) -> dict[str, Any]:
    """Check if requested slot is open or suggest alternatives."""
    try:
        service = parse_service_type(service_type)
        if service.requires_human_quote:
            return {
                "available": False,
                "reason": (
                    "Ceramic Coating requires a multi-day custom inspection "
                    "and quote from the shop manager."
                ),
                "requires_escalation": True,
            }

        duration = service.duration_minutes
        is_free = calendar.check_slot_availability(date, time, duration)

        if is_free:
            return {
                "available": True,
                "date": date,
                "time": time,
                "duration_minutes": duration,
                "service": service.value,
                "message": f"{time} on {date} is open for {service.value} ({duration} mins).",
            }

        alternatives = calendar.find_alternative_slots(date, time, duration, limit=3)
        return {
            "available": False,
            "date": date,
            "requested_time": time,
            "duration_minutes": duration,
            "service": service.value,
            "reason": "Requested slot is unavailable (booked or outside shop hours).",
            "alternative_slots": alternatives,
            "message": (
                f"{time} on {date} is unavailable. Closest available open slots: "
                f"{', '.join(alternatives) if alternatives else 'None on this date'}."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error checking availability: %s", exc)
        return {"available": False, "error": str(exc)}


def book_appointment(
    calendar: CalendarAdapter,
    sheets: SheetsAdapter,
    customer_name: str,
    phone_number: str,
    date: str,
    time: str,
    service_type: str,
    vehicle_type: str,
) -> dict[str, Any]:
    """Book a new appointment, sync Calendar, and log to Sheets."""
    try:
        # Check oversized vehicle boundary
        if is_oversized_vehicle(vehicle_type):
            return {
                "success": False,
                "requires_escalation": True,
                "reason": (
                    f"Vehicle '{vehicle_type}' is oversized/special and requires "
                    "a custom size review from our shop manager."
                ),
            }

        service = parse_service_type(service_type)
        if service.requires_human_quote:
            return {
                "success": False,
                "requires_escalation": True,
                "reason": "Ceramic Coating requires a custom consultation with the shop manager.",
            }

        duration = service.duration_minutes
        is_free = calendar.check_slot_availability(date, time, duration)

        if not is_free:
            alternatives = calendar.find_alternative_slots(date, time, duration, limit=3)
            return {
                "success": False,
                "reason": f"Slot {time} on {date} is no longer available.",
                "alternative_slots": alternatives,
            }

        target_date = parse_date_string(date)
        target_time = parse_time_string(time)
        start_dt = datetime.combine(target_date, target_time)
        end_dt = start_dt + timedelta(minutes=duration)

        # 1. Create Calendar Event
        appointment = calendar.create_appointment_event(
            customer_name=customer_name,
            phone=phone_number,
            service=service,
            vehicle_type=vehicle_type,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        # 2. Upsert Customer Contact in Google Sheets
        sheets.upsert_contact(
            phone_number=phone_number,
            customer_name=customer_name,
            vehicle_type=vehicle_type,
            is_booking=True,
        )

        # 3. Append Audit Log in Google Sheets
        price, _ = service.get_price(vehicle_type)
        log = CallLog(
            timestamp=datetime.now().isoformat(),
            caller_phone=phone_number,
            caller_name=customer_name,
            call_intent=CallIntent.BOOKING,
            outcome=f"Booked {service.value} on {date} at {time} for ${price}",
            needs_human_followup=False,
            summary=f"Confirmed appointment for {customer_name} ({vehicle_type}).",
        )
        sheets.append_call_log(log)

        return {
            "success": True,
            "appointment_id": appointment.id,
            "customer_name": customer_name,
            "service": service.value,
            "vehicle_type": vehicle_type,
            "date": date,
            "time": time,
            "duration_minutes": duration,
            "price_dollars": price,
            "preparation_guidelines": PREPARATION_GUIDELINES,
            "message": (
                f"Successfully booked {service.value} for {customer_name} on {date} at {time}. "
                f"Base price: ${price}."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error booking appointment: %s", exc)
        return {"success": False, "error": str(exc)}


def reschedule_appointment(
    calendar: CalendarAdapter,
    sheets: SheetsAdapter,
    customer_name: str,
    phone_number: str,
    current_date: str,
    new_date: str,
    new_time: str,
) -> dict[str, Any]:
    """Reschedule an existing appointment."""
    try:
        # 1. Locate existing appointment
        existing = calendar.find_appointment_by_phone(phone_number, current_date)
        if not existing:
            return {
                "success": False,
                "reason": (
                    f"No active appointment found for phone {phone_number} on {current_date}."
                ),
            }

        # 2. Check availability of new slot
        duration = int((existing.end_time - existing.start_time).total_seconds() / 60)
        is_free = calendar.check_slot_availability(new_date, new_time, duration)

        if not is_free:
            alternatives = calendar.find_alternative_slots(new_date, new_time, duration, limit=3)
            return {
                "success": False,
                "reason": f"New slot {new_time} on {new_date} is busy.",
                "alternative_slots": alternatives,
            }

        # 3. Update Calendar Event
        target_date = parse_date_string(new_date)
        target_time = parse_time_string(new_time)
        new_start_dt = datetime.combine(target_date, target_time)
        new_end_dt = new_start_dt + timedelta(minutes=duration)

        assert existing.id is not None
        calendar.update_appointment_event(existing.id, new_start_dt, new_end_dt)

        # 4. Log Reschedule to Sheets
        log = CallLog(
            timestamp=datetime.now().isoformat(),
            caller_phone=phone_number,
            caller_name=customer_name or existing.customer_name,
            call_intent=CallIntent.RESCHEDULE,
            outcome=f"Rescheduled to {new_date} at {new_time}",
            needs_human_followup=False,
            summary=f"Shifted booking from {current_date} to {new_date} {new_time}.",
        )
        sheets.append_call_log(log)

        return {
            "success": True,
            "customer_name": customer_name or existing.customer_name,
            "new_date": new_date,
            "new_time": new_time,
            "message": f"Appointment successfully rescheduled to {new_date} at {new_time}.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error rescheduling appointment: %s", exc)
        return {"success": False, "error": str(exc)}


def cancel_appointment(
    calendar: CalendarAdapter,
    sheets: SheetsAdapter,
    customer_name: str,
    phone_number: str,
    date: str,
    reason: str = "Customer request",
) -> dict[str, Any]:
    """Cancel an appointment."""
    try:
        existing = calendar.find_appointment_by_phone(phone_number, date)
        if not existing:
            return {
                "success": False,
                "reason": f"No active appointment found for {phone_number} on {date}.",
            }

        assert existing.id is not None
        calendar.cancel_appointment_event(existing.id)

        # Audit log in sheets
        log = CallLog(
            timestamp=datetime.now().isoformat(),
            caller_phone=phone_number,
            caller_name=customer_name or existing.customer_name,
            call_intent=CallIntent.CANCELLATION,
            outcome=f"Cancelled appointment on {date}. Reason: {reason}",
            needs_human_followup=False,
            summary=f"Cancelled appointment. Reason: {reason}",
        )
        sheets.append_call_log(log)

        return {
            "success": True,
            "message": f"Appointment on {date} has been successfully cancelled.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error cancelling appointment: %s", exc)
        return {"success": False, "error": str(exc)}


def report_running_late(
    calendar: CalendarAdapter,
    sheets: SheetsAdapter,
    customer_name: str,
    phone_number: str,
    minutes_late: int,
) -> dict[str, Any]:
    """Handle late customer arrival notification."""
    try:
        existing = calendar.find_appointment_by_phone(phone_number)
        log = CallLog(
            timestamp=datetime.now().isoformat(),
            caller_phone=phone_number,
            caller_name=customer_name or (existing.customer_name if existing else "Customer"),
            call_intent=CallIntent.RUNNING_LATE,
            outcome=f"Reported {minutes_late} minutes late",
            needs_human_followup=minutes_late > 15,
            summary=f"Customer notified running late by {minutes_late} minutes.",
        )
        sheets.append_call_log(log)

        if minutes_late <= 15:
            return {
                "accommodated": True,
                "minutes_late": minutes_late,
                "message": (
                    f"Thanks for letting us know! A delay of {minutes_late} minutes is within our "
                    "15-minute grace period. Your detailers will be ready when you arrive."
                ),
            }

        return {
            "accommodated": False,
            "minutes_late": minutes_late,
            "message": (
                f"A delay of {minutes_late} minutes exceeds our 15-minute grace period and may "
                "impact subsequent appointments. We can either adjust your service to an "
                "Express Wash & Vac (45 mins) or reschedule you to a later open slot."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error reporting late arrival: %s", exc)
        return {"accommodated": False, "error": str(exc)}


def escalate_to_human(
    sheets: SheetsAdapter,
    customer_name: str,
    phone_number: str,
    reason: str,
    details: str,
) -> dict[str, Any]:
    """Log mandatory human manager escalation."""
    try:
        # Match reason
        matched_intent = CallIntent.COMPLAINT
        if "fleet" in reason.lower():
            matched_intent = CallIntent.INQUIRY

        # Upsert contact
        sheets.upsert_contact(
            phone_number=phone_number,
            customer_name=customer_name,
            vehicle_type="Standard",
            notes=f"Escalation [{reason}]: {details}",
            is_booking=False,
        )

        # Log with needs_human_followup=True
        log = CallLog(
            timestamp=datetime.now().isoformat(),
            caller_phone=phone_number,
            caller_name=customer_name,
            call_intent=matched_intent,
            outcome=f"Escalated to human manager: {reason}",
            needs_human_followup=True,
            summary=f"Manager follow-up required. Details: {details}",
        )
        sheets.append_call_log(log)

        return {
            "escalated": True,
            "customer_name": customer_name,
            "phone_number": phone_number,
            "reason": reason,
            "message": (
                f"I have logged this for our shop manager under '{reason}'. "
                f"Our manager will review the details and call you at {phone_number} promptly."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error escalating to human: %s", exc)
        return {"escalated": False, "error": str(exc)}


# ==============================================================================
# Gemini Tool Declarations
# ==============================================================================

GEMINI_TOOLS_SCHEMA = [
    {
        "name": "check_availability",
        "description": "Check if an appointment slot is available or retrieve alternative slots.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {
                    "type": "STRING",
                    "description": "Target date in YYYY-MM-DD format (e.g. '2026-10-15').",
                },
                "time": {
                    "type": "STRING",
                    "description": "Requested start time (e.g. '10:00 AM' or '15:30').",
                },
                "service_type": {
                    "type": "STRING",
                    "description": "Name of service (Express Wash, Interior Detail, Full Detail).",
                },
            },
            "required": ["date", "time", "service_type"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book a confirmed appointment in Google Calendar and Google Sheets.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "Customer full name."},
                "phone_number": {"type": "STRING", "description": "Customer contact phone."},
                "date": {"type": "STRING", "description": "Appointment date (YYYY-MM-DD)."},
                "time": {"type": "STRING", "description": "Start time (e.g. '10:00 AM')."},
                "service_type": {
                    "type": "STRING",
                    "description": "Service name (Express Wash, Interior Detail, Full Detail).",
                },
                "vehicle_type": {
                    "type": "STRING",
                    "description": "Vehicle model or category (Sedan, SUV, Truck, Minivan).",
                },
            },
            "required": [
                "customer_name",
                "phone_number",
                "date",
                "time",
                "service_type",
                "vehicle_type",
            ],
        },
    },
    {
        "name": "reschedule_appointment",
        "description": "Reschedule an existing appointment to a new date and time.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "Customer name."},
                "phone_number": {"type": "STRING", "description": "Customer phone number."},
                "current_date": {
                    "type": "STRING",
                    "description": "Existing appointment date (YYYY-MM-DD).",
                },
                "new_date": {"type": "STRING", "description": "New requested date (YYYY-MM-DD)."},
                "new_time": {"type": "STRING", "description": "New start time (e.g. '2:00 PM')."},
            },
            "required": ["customer_name", "phone_number", "current_date", "new_date", "new_time"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "Customer name."},
                "phone_number": {"type": "STRING", "description": "Customer phone number."},
                "date": {"type": "STRING", "description": "Appointment date (YYYY-MM-DD)."},
                "reason": {
                    "type": "STRING",
                    "description": "Reason for cancellation.",
                },
            },
            "required": ["customer_name", "phone_number", "date"],
        },
    },
    {
        "name": "report_running_late",
        "description": "Report that a customer is running late for their appointment.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "Customer name."},
                "phone_number": {"type": "STRING", "description": "Customer phone number."},
                "minutes_late": {
                    "type": "INTEGER",
                    "description": "Estimated minutes customer will be delayed.",
                },
            },
            "required": ["customer_name", "phone_number", "minutes_late"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate billing disputes, damage claims, or fleet quotes to manager.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "customer_name": {"type": "STRING", "description": "Customer name."},
                "phone_number": {"type": "STRING", "description": "Customer phone number."},
                "reason": {
                    "type": "STRING",
                    "description": "Escalation category (Billing Dispute, Damage, Fleet).",
                },
                "details": {
                    "type": "STRING",
                    "description": "Detailed explanation of the customer situation.",
                },
            },
            "required": ["customer_name", "phone_number", "reason", "details"],
        },
    },
]


def get_groq_tools_schema() -> list[dict[str, Any]]:
    """Convert tool declarations into OpenAI/Groq standard function calling schema."""
    groq_tools: list[dict[str, Any]] = []
    for tool in GEMINI_TOOLS_SCHEMA:
        props: dict[str, Any] = {}
        for prop_name, prop_spec in tool["parameters"]["properties"].items():
            raw_type = prop_spec.get("type", "STRING").lower()
            schema_type = "integer" if raw_type in ("integer", "int") else "string"
            props[prop_name] = {
                "type": schema_type,
                "description": prop_spec.get("description", ""),
            }
        groq_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": tool["parameters"].get("required", []),
                    },
                },
            }
        )
    return groq_tools


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    calendar: CalendarAdapter,
    sheets: SheetsAdapter,
) -> dict[str, Any]:
    """Dispatch tool call by name with given arguments."""
    match tool_name:
        case "check_availability":
            return check_availability(
                calendar=calendar,
                date=arguments.get("date", ""),
                time=arguments.get("time", ""),
                service_type=arguments.get("service_type") or arguments.get("service", ""),
            )
        case "book_appointment":
            return book_appointment(
                calendar=calendar,
                sheets=sheets,
                customer_name=arguments.get("customer_name") or arguments.get("name", ""),
                phone_number=arguments.get("phone_number") or arguments.get("phone", ""),
                date=arguments.get("date", ""),
                time=arguments.get("time", ""),
                service_type=arguments.get("service_type") or arguments.get("service", ""),
                vehicle_type=arguments.get("vehicle_type") or arguments.get("vehicle", ""),
            )
        case "reschedule_appointment":
            return reschedule_appointment(
                calendar=calendar,
                sheets=sheets,
                customer_name=arguments.get("customer_name") or arguments.get("name", ""),
                phone_number=arguments.get("phone_number") or arguments.get("phone", ""),
                current_date=arguments.get("current_date", ""),
                new_date=arguments.get("new_date", ""),
                new_time=arguments.get("new_time", ""),
            )
        case "cancel_appointment":
            return cancel_appointment(
                calendar=calendar,
                sheets=sheets,
                customer_name=arguments.get("customer_name") or arguments.get("name", ""),
                phone_number=arguments.get("phone_number") or arguments.get("phone", ""),
                date=arguments.get("date", ""),
                reason=arguments.get("reason", "Customer request"),
            )
        case "report_running_late":
            return report_running_late(
                calendar=calendar,
                sheets=sheets,
                customer_name=arguments.get("customer_name") or arguments.get("name", ""),
                phone_number=arguments.get("phone_number") or arguments.get("phone", ""),
                minutes_late=int(arguments.get("minutes_late", 0)),
            )
        case "escalate_to_human":
            return escalate_to_human(
                sheets=sheets,
                customer_name=arguments.get("customer_name") or arguments.get("name", ""),
                phone_number=arguments.get("phone_number") or arguments.get("phone", ""),
                reason=arguments.get("reason", EscalationReason.CUSTOMER_REQUEST.value),
                details=arguments.get("details", ""),
            )
        case _:
            return {"error": f"Unknown tool: '{tool_name}'"}
