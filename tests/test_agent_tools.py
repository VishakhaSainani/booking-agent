"""Unit tests for agent tools and conversational flow."""

from cedar_lane_ai.adapters import InMemoryCalendarAdapter, InMemorySheetsAdapter
from cedar_lane_ai.services import (
    ReceptionistAgent,
    book_appointment,
    cancel_appointment,
    check_availability,
    escalate_to_human,
    report_running_late,
    reschedule_appointment,
)


def test_tool_check_availability() -> None:
    """Verify check_availability identifies open slots and alternatives."""
    cal = InMemoryCalendarAdapter()
    test_date = "2026-10-15"

    # Slot is open
    res = check_availability(cal, test_date, "10:00 AM", "Express Wash & Vac")
    assert res["available"] is True

    # Book slot
    cal.create_appointment_event(
        customer_name="Existing Customer",
        phone="5551112222",
        service="Express Wash & Vac",
        vehicle_type="Sedan",
        start_dt=cal.list_day_events(test_date)[0].start_time
        if cal.list_day_events(test_date)
        else None or __import__("datetime").datetime(2026, 10, 15, 10, 0),
        end_dt=__import__("datetime").datetime(2026, 10, 15, 10, 45),
    )

    # Now slot is unavailable and provides alternative suggestions
    res2 = check_availability(cal, test_date, "10:00 AM", "Express Wash & Vac")
    assert res2["available"] is False
    assert len(res2["alternative_slots"]) > 0

    # Ceramic coating requires escalation
    res3 = check_availability(cal, test_date, "10:00 AM", "Ceramic Coating")
    assert res3["available"] is False
    assert res3["requires_escalation"] is True


def test_tool_book_appointment_lifecycle() -> None:
    """Verify booking creates calendar event, contacts entry, and call log."""
    cal = InMemoryCalendarAdapter()
    sheets = InMemorySheetsAdapter()
    test_date = "2026-10-15"

    # 1. Oversized vehicle rejection
    res_oversized = book_appointment(
        cal,
        sheets,
        customer_name="Commercial Client",
        phone_number="5550001111",
        date=test_date,
        time="09:00 AM",
        service_type="Full Detail",
        vehicle_type="Lifted Dually Truck",
    )
    assert res_oversized["success"] is False
    assert res_oversized["requires_escalation"] is True

    # 2. Valid booking
    res = book_appointment(
        cal,
        sheets,
        customer_name="Jane Doe",
        phone_number="5554443333",
        date=test_date,
        time="09:00 AM",
        service_type="Express Wash & Vac",
        vehicle_type="SUV",
    )
    assert res["success"] is True
    assert res["price_dollars"] == 70  # $70 for SUV Express Wash
    assert len(res["preparation_guidelines"]) > 0

    # Verify calendar has event
    events = cal.list_day_events(test_date)
    assert len(events) == 1
    assert events[0].customer_name == "Jane Doe"

    # Verify Sheets Contacts
    contact = sheets.get_contact("5554443333")
    assert contact is not None
    assert contact.customer_name == "Jane Doe"
    assert contact.total_bookings == 1

    # Verify Sheets Call Logs
    logs = sheets.list_call_logs()
    assert len(logs) == 1
    assert logs[0].caller_name == "Jane Doe"
    assert logs[0].needs_human_followup is False


def test_tool_reschedule_and_cancel() -> None:
    """Verify reschedule and cancel tools update both calendar and sheets."""
    cal = InMemoryCalendarAdapter()
    sheets = InMemorySheetsAdapter()
    curr_date = "2026-10-15"
    new_date = "2026-10-16"

    # Create initial booking
    book_appointment(
        cal,
        sheets,
        customer_name="Mark Evans",
        phone_number="5558889999",
        date=curr_date,
        time="11:00 AM",
        service_type="Interior Detail & Wash",
        vehicle_type="Sedan",
    )

    # Reschedule
    res_resched = reschedule_appointment(
        cal,
        sheets,
        customer_name="Mark Evans",
        phone_number="5558889999",
        current_date=curr_date,
        new_date=new_date,
        new_time="02:00 PM",
    )
    assert res_resched["success"] is True

    # Cancel
    res_cancel = cancel_appointment(
        cal,
        sheets,
        customer_name="Mark Evans",
        phone_number="5558889999",
        date=new_date,
        reason="Family emergency",
    )
    assert res_cancel["success"] is True


def test_tool_report_running_late() -> None:
    """Verify running late policy: <= 15 min accommodated, > 15 min suggests alternatives."""
    cal = InMemoryCalendarAdapter()
    sheets = InMemorySheetsAdapter()

    # <= 15 minutes
    res1 = report_running_late(cal, sheets, "Dave", "5551239999", minutes_late=10)
    assert res1["accommodated"] is True
    assert "grace period" in res1["message"]

    # > 15 minutes
    res2 = report_running_late(cal, sheets, "Dave", "5551239999", minutes_late=25)
    assert res2["accommodated"] is False
    assert "exceeds our 15-minute grace period" in res2["message"]


def test_tool_escalate_to_human() -> None:
    """Verify human escalation tags call log with needs_human_followup=True."""
    sheets = InMemorySheetsAdapter()
    res = escalate_to_human(
        sheets=sheets,
        customer_name="Angry Customer",
        phone_number="5559991111",
        reason="Billing Dispute",
        details="Caller claimed an unauthorized $50 surcharge on last invoice.",
    )
    assert res["escalated"] is True

    logs = sheets.list_call_logs()
    assert len(logs) == 1
    assert logs[0].needs_human_followup is True
    assert logs[0].caller_name == "Angry Customer"


def test_receptionist_agent_offline_turn() -> None:
    """Verify ReceptionistAgent handles conversational turns gracefully without live LLM calls."""
    cal = InMemoryCalendarAdapter()
    sheets = InMemorySheetsAdapter()
    agent = ReceptionistAgent(calendar=cal, sheets=sheets, client=None)

    # Ask about hours
    reply1, hist1, _ = agent.process_turn("What are your shop hours?")
    assert "8:00 AM to 6:00 PM" in reply1
    assert "closed on Sundays" in reply1

    # Ask about prep
    reply2, hist2, _ = agent.process_turn("How should I prepare my car before dropping it off?")
    assert "personal belongings" in reply2

    # Disputed charge escalation
    complaint_msg = "I have an incorrect charge on my bill from yesterday!"
    reply3, hist3, events = agent.process_turn(complaint_msg)
    assert "manager" in reply3.lower()
    assert len(events) == 1
    assert events[0]["tool_name"] == "escalate_to_human"
