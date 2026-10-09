"""Unit tests for CalendarAdapter and scheduling engine."""

from datetime import datetime

from cedar_lane_ai.adapters import InMemoryCalendarAdapter, get_calendar_adapter
from cedar_lane_ai.domain import ServiceType


def test_calendar_adapter_factory() -> None:
    """Verify factory returns InMemoryCalendarAdapter in test/mock mode."""
    adapter = get_calendar_adapter(force_fresh=True)
    assert isinstance(adapter, InMemoryCalendarAdapter)


def test_slot_collision_and_availability() -> None:
    """Verify interval collision detection and operating hours enforcement."""
    adapter = InMemoryCalendarAdapter()
    test_date = "2026-10-15"  # Thursday

    # Initial check: 10:00 AM for 90 mins should be open
    assert adapter.check_slot_availability(test_date, "10:00 AM", 90) is True

    # Book 10:00 AM to 11:30 AM
    start_dt = datetime(2026, 10, 15, 10, 0)
    end_dt = datetime(2026, 10, 15, 11, 30)
    apt = adapter.create_appointment_event(
        customer_name="John Doe",
        phone="+15550001111",
        service=ServiceType.INTERIOR_DETAIL,
        vehicle_type="Sedan",
        start_dt=start_dt,
        end_dt=end_dt,
    )
    assert apt.id is not None

    # Now verify collision checks:
    # 1. Exact same start time -> Busy
    assert adapter.check_slot_availability(test_date, "10:00 AM", 90) is False
    # 2. Starting during the event (10:30 AM) -> Busy
    assert adapter.check_slot_availability(test_date, "10:30 AM", 45) is False
    # 3. Starting before but ending during the event (9:30 AM for 45 mins -> ends 10:15) -> Busy
    assert adapter.check_slot_availability(test_date, "9:30 AM", 45) is False
    # 4. Adjacent slots: ending right as event starts (9:00 AM for 60 mins -> ends 10:00) -> Open
    assert adapter.check_slot_availability(test_date, "09:00 AM", 60) is True
    # 5. Starting right when event ends (11:30 AM for 45 mins) -> Open
    assert adapter.check_slot_availability(test_date, "11:30 AM", 45) is True


def test_find_alternative_slots() -> None:
    """Verify alternative slot suggestions rank closest open slots."""
    adapter = InMemoryCalendarAdapter()
    test_date = "2026-10-15"  # Thursday

    # Pre-book 3:30 PM to 5:00 PM (Interior Detail, 90 mins)
    adapter.create_appointment_event(
        customer_name="Existing Customer",
        phone="+15559998888",
        service=ServiceType.INTERIOR_DETAIL,
        vehicle_type="Sedan",
        start_dt=datetime(2026, 10, 15, 15, 30),
        end_dt=datetime(2026, 10, 15, 17, 0),
    )

    # 3:30 PM is booked, ask for alternative slots for a 90-minute service
    alternatives = adapter.find_alternative_slots(
        test_date, "3:30 PM", duration_minutes=90, limit=3
    )
    assert len(alternatives) == 3
    # 3:30 PM itself must not be in the alternatives
    assert "03:30 PM" not in alternatives
    # 4:00 PM overlaps; 4:30 PM + 90m = 6:00 PM (fits).
    # 2:00 PM (ends at 3:30 PM) is an immediate adjacent open slot!
    assert "02:00 PM" in alternatives


def test_reschedule_and_cancellation() -> None:
    """Verify rescheduling frees the previous slot and cancellation frees the event."""
    adapter = InMemoryCalendarAdapter()
    test_date = "2026-10-16"  # Friday

    # Create appointment at 10:00 AM - 10:45 AM
    apt = adapter.create_appointment_event(
        customer_name="Bob Brown",
        phone="+15552223333",
        service=ServiceType.EXPRESS_WASH,
        vehicle_type="SUV",
        start_dt=datetime(2026, 10, 16, 10, 0),
        end_dt=datetime(2026, 10, 16, 10, 45),
    )
    assert adapter.check_slot_availability(test_date, "10:00 AM", 45) is False

    # Reschedule to 2:00 PM - 2:45 PM
    assert apt.id is not None
    adapter.update_appointment_event(
        apt.id,
        new_start_dt=datetime(2026, 10, 16, 14, 0),
        new_end_dt=datetime(2026, 10, 16, 14, 45),
    )

    # 10:00 AM is now free again!
    assert adapter.check_slot_availability(test_date, "10:00 AM", 45) is True
    # 2:00 PM is now busy
    assert adapter.check_slot_availability(test_date, "2:00 PM", 45) is False

    # Cancel the appointment
    cancelled = adapter.cancel_appointment_event(apt.id)
    assert cancelled is True
    # 2:00 PM is now free again!
    assert adapter.check_slot_availability(test_date, "2:00 PM", 45) is True


def test_find_appointment_by_phone() -> None:
    """Verify phone lookup finds active customer appointment."""
    adapter = InMemoryCalendarAdapter()
    adapter.create_appointment_event(
        customer_name="Carol White",
        phone="+1 (555) 333-4444",
        service=ServiceType.FULL_DETAIL,
        vehicle_type="Sedan",
        start_dt=datetime(2026, 10, 17, 9, 0),
        end_dt=datetime(2026, 10, 17, 12, 0),
    )

    # Search with different formatting
    found = adapter.find_appointment_by_phone("5553334444")
    assert found is not None
    assert found.customer_name == "Carol White"

    # Search non-existent
    not_found = adapter.find_appointment_by_phone("9999999999")
    assert not_found is None
