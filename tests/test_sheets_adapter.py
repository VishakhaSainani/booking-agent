"""Unit tests for SheetsAdapter customer directory and call logs."""

from cedar_lane_ai.adapters import InMemorySheetsAdapter, get_sheets_adapter
from cedar_lane_ai.domain import CallIntent, CallLog


def test_sheets_adapter_factory() -> None:
    """Verify factory returns InMemorySheetsAdapter in test/mock mode."""
    adapter = get_sheets_adapter(force_fresh=True)
    assert isinstance(adapter, InMemorySheetsAdapter)


def test_contact_upsert_and_phone_normalization() -> None:
    """Verify customer upsert updates details, normalizes phone, and prevents duplicates."""
    adapter = InMemorySheetsAdapter()

    # Initial booking for Alice
    contact1 = adapter.upsert_contact(
        phone_number="+1 (555) 123-4567",
        customer_name="Alice Smith",
        vehicle_type="Honda Civic Sedan",
        notes="Prefers fragrance-free soap",
        is_booking=True,
        email="alice@example.com",
    )
    assert contact1.contact_id == "con_001"
    assert contact1.total_bookings == 1
    assert contact1.name == "Alice Smith"
    assert contact1.email == "alice@example.com"
    assert contact1.created_at != ""
    assert contact1.last_call_at != ""

    # Second booking using differently formatted phone string (repeat caller)
    contact2 = adapter.upsert_contact(
        phone_number="5551234567",
        customer_name="Alice Smith",
        vehicle_type="Honda Civic Sedan",
        notes="Requested trunk vacuum",
        is_booking=True,
    )
    # Must preserve stable contact_id and created_at
    assert contact2.contact_id == "con_001"
    assert contact2.total_bookings == 2
    assert "fragrance-free soap" in contact2.notes
    assert "trunk vacuum" in contact2.notes
    assert contact2.created_at == contact1.created_at

    # Verify query and no duplicate rows created
    contacts = adapter.list_contacts()
    assert len(contacts) == 1
    found = adapter.get_contact("555-123-4567")
    assert found is not None
    assert found.contact_id == "con_001"
    assert found.total_bookings == 2


def test_call_logs_append_and_escalation() -> None:
    """Verify audit trail logging, contact_id linkage, and human follow-up tagging."""
    adapter = InMemorySheetsAdapter()

    # Ensure contact exists first
    contact = adapter.upsert_contact(
        phone_number="5551112222",
        customer_name="Bob Jones",
    )

    log1 = CallLog(
        contact_id=contact.contact_id,
        phone="5551112222",
        started_at="2026-10-08T10:00:00Z",
        channel="chat",
        intent=CallIntent.BOOKING.value,
        outcome="Booked Express Wash",
        appointment_id="cal_evt_12345",
        handoff_required=False,
        summary="Customer booked 10am slot.",
        status="completed",
    )
    adapter.append_call_log(log1)

    # Escalated call
    log2 = CallLog(
        phone="5559990000",
        started_at="2026-10-08T10:15:00Z",
        channel="phone",
        intent=CallIntent.COMPLAINT.value,
        outcome="Billing dispute escalated to human manager callback",
        appointment_id=None,
        handoff_required=True,
        handoff_reason="Billing dispute ($150 charge)",
        summary="Customer contested $150 charge from last week.",
        status="unresolved",
    )
    adapter.append_call_log(log2)

    logs = adapter.list_call_logs(limit=10)
    assert len(logs) == 2
    # Newest log first
    escalated = logs[0]
    assert escalated.phone == "5559990000"
    assert escalated.handoff_required is True
    assert escalated.handoff_reason == "Billing dispute ($150 charge)"
    assert escalated.status == "unresolved"
    assert escalated.channel == "phone"
    assert escalated.contact_id != ""  # Auto-linked or created contact

    booking = logs[1]
    assert booking.phone == "5551112222"
    assert booking.contact_id == contact.contact_id
    assert booking.appointment_id == "cal_evt_12345"
    assert booking.handoff_required is False
    assert booking.status == "completed"


def test_repeated_calls_updates_contact_and_appends_call_log() -> None:
    """Verify repeated calls maintain one contact row while appending distinct call log rows."""
    adapter = InMemorySheetsAdapter()
    phone = "+1 (415) 555-0190"

    # Call 1: Pricing inquiry
    c1 = adapter.upsert_contact(
        phone_number=phone,
        customer_name="Sara",
        notes="Owns an SUV",
        is_booking=False,
    )
    assert c1.contact_id == "con_001"
    assert c1.name == "Sara"

    adapter.append_call_log(
        CallLog(
            contact_id=c1.contact_id,
            phone=phone,
            channel="phone",
            intent="Pricing",
            summary="Asked for SUV interior detail price",
            outcome="Provided quote $190",
            status="completed",
        )
    )

    # Call 2: Booking appointment
    c2 = adapter.upsert_contact(
        phone_number=phone,
        customer_name="Sara",
        notes="Prefers afternoon slots",
        is_booking=True,
    )
    assert c2.contact_id == c1.contact_id  # Same contact ID preserved
    assert c2.total_bookings == 1
    assert "Owns an SUV" in c2.notes
    assert "Prefers afternoon slots" in c2.notes

    adapter.append_call_log(
        CallLog(
            contact_id=c2.contact_id,
            phone=phone,
            channel="phone",
            intent="Booking",
            summary="Booked Interior Detail on Thursday 2:00 PM",
            outcome="Booked",
            appointment_id="cal_evt_thurs_1400",
            status="completed",
        )
    )

    # Call 3: Billing question (escalated)
    c3 = adapter.upsert_contact(
        phone_number=phone,
        customer_name="Sara",
        notes="Disputed charge",
        is_booking=False,
    )
    assert c3.contact_id == c1.contact_id

    adapter.append_call_log(
        CallLog(
            contact_id=c3.contact_id,
            phone=phone,
            channel="phone",
            intent="Complaint",
            summary="Billing question on prior service",
            outcome="Escalated to shop manager",
            handoff_required=True,
            handoff_reason="Billing question",
            status="unresolved",
        )
    )

    # Verification:
    # 1. Contacts has strictly 1 entry for this caller
    contacts = adapter.list_contacts()
    assert len(contacts) == 1
    assert contacts[0].contact_id == "con_001"
    assert contacts[0].name == "Sara"
    assert contacts[0].total_bookings == 1

    # 2. Call Logs has 3 separate records, all sharing the same contact_id
    call_logs = adapter.list_call_logs(limit=10)
    assert len(call_logs) == 3
    for log in call_logs:
        assert log.contact_id == "con_001"
        assert log.channel == "phone"

    # Verify chronological/order outcomes
    intents = [log.intent for log in reversed(call_logs)]
    assert intents == ["Pricing", "Booking", "Complaint"]
    reversed_logs = list(reversed(call_logs))
    assert reversed_logs[1].appointment_id == "cal_evt_thurs_1400"
    assert reversed_logs[2].handoff_required is True
    assert reversed_logs[2].handoff_reason == "Billing question"


