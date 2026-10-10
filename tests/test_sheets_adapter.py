"""Unit tests for SheetsAdapter customer directory and call logs."""

from cedar_lane_ai.adapters import InMemorySheetsAdapter, get_sheets_adapter
from cedar_lane_ai.domain import CallIntent, CallLog


def test_sheets_adapter_factory() -> None:
    """Verify factory returns InMemorySheetsAdapter in test/mock mode."""
    adapter = get_sheets_adapter(force_fresh=True)
    assert isinstance(adapter, InMemorySheetsAdapter)


def test_contact_upsert_and_phone_normalization() -> None:
    """Verify customer upsert updates details, normalizes phone, and increments bookings."""
    adapter = InMemorySheetsAdapter()

    # Initial booking for Alice
    contact1 = adapter.upsert_contact(
        phone_number="+1 (555) 123-4567",
        customer_name="Alice Smith",
        vehicle_type="Honda Civic Sedan",
        notes="Prefers fragrance-free soap",
        is_booking=True,
    )
    assert contact1.total_bookings == 1
    assert contact1.customer_name == "Alice Smith"

    # Second booking using differently formatted phone string
    contact2 = adapter.upsert_contact(
        phone_number="5551234567",
        customer_name="Alice Smith",
        vehicle_type="Honda Civic Sedan",
        notes="Requested trunk vacuum",
        is_booking=True,
    )
    assert contact2.total_bookings == 2
    assert "fragrance-free soap" in contact2.notes
    assert "trunk vacuum" in contact2.notes

    # Verify query
    found = adapter.get_contact("555-123-4567")
    assert found is not None
    assert found.total_bookings == 2


def test_call_logs_append_and_escalation() -> None:
    """Verify audit trail logging and human follow-up tagging."""
    adapter = InMemorySheetsAdapter()

    log1 = CallLog(
        timestamp="2026-10-08T10:00:00Z",
        caller_phone="5551112222",
        caller_name="Bob Jones",
        call_intent=CallIntent.BOOKING,
        outcome="Booked Express Wash",
        needs_human_followup=False,
        summary="Customer booked 10am slot.",
    )
    adapter.append_call_log(log1)

    # Escalated call
    log2 = CallLog(
        timestamp="2026-10-08T10:15:00Z",
        caller_phone="5559990000",
        caller_name="Charlie Danger",
        call_intent=CallIntent.COMPLAINT,
        outcome="Billing dispute escalated to human manager callback",
        needs_human_followup=True,
        summary="Customer contested $150 charge from last week.",
    )
    adapter.append_call_log(log2)

    logs = adapter.list_call_logs(limit=10)
    assert len(logs) == 2
    # Newest log first
    assert logs[0].caller_name == "Charlie Danger"
    assert logs[0].needs_human_followup is True
    assert logs[1].caller_name == "Bob Jones"
    assert logs[1].needs_human_followup is False
