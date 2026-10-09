"""Unit tests for domain models, pricing rules, operating hours, and vehicle classification."""

from datetime import datetime

from cedar_lane_ai.domain import (
    CallIntent,
    CallLog,
    Contact,
    ServiceType,
    ShopHours,
    VehicleType,
    is_oversized_vehicle,
)


def test_service_pricing_and_durations() -> None:
    """Test standard durations and vehicle-specific pricing."""
    # Express Wash & Vac (45 min)
    assert ServiceType.EXPRESS_WASH.duration_minutes == 45
    assert ServiceType.EXPRESS_WASH.get_price(VehicleType.SEDAN) == (50, False)
    assert ServiceType.EXPRESS_WASH.get_price(VehicleType.SUV) == (70, False)
    assert ServiceType.EXPRESS_WASH.get_price(VehicleType.PICKUP_TRUCK) == (70, False)

    # Interior Detail & Wash (90 min)
    assert ServiceType.INTERIOR_DETAIL.duration_minutes == 90
    assert ServiceType.INTERIOR_DETAIL.get_price(VehicleType.SEDAN) == (150, False)
    assert ServiceType.INTERIOR_DETAIL.get_price(VehicleType.SUV) == (190, False)

    # Full Detail (180 min)
    assert ServiceType.FULL_DETAIL.duration_minutes == 180
    assert ServiceType.FULL_DETAIL.get_price(VehicleType.SEDAN) == (250, False)
    assert ServiceType.FULL_DETAIL.get_price(VehicleType.SUV) == (320, False)

    # Ceramic Coating ($800+, custom quote)
    assert ServiceType.CERAMIC_COATING.requires_human_quote is True
    assert ServiceType.CERAMIC_COATING.get_price(VehicleType.SEDAN) == (800, True)


def test_vehicle_classification_oversized() -> None:
    """Verify oversized vehicles are flagged for manager quote."""
    # Standard vehicles
    assert is_oversized_vehicle(VehicleType.SEDAN) is False
    assert is_oversized_vehicle(VehicleType.SUV) is False
    assert is_oversized_vehicle("Honda Civic Sedan") is False
    assert is_oversized_vehicle("Toyota RAV4 Crossover") is False

    # Oversized vehicles
    assert is_oversized_vehicle(VehicleType.COMMERCIAL_CARGO_VAN) is True
    assert is_oversized_vehicle(VehicleType.RV) is True
    assert is_oversized_vehicle(VehicleType.BOAT) is True
    assert is_oversized_vehicle("Ford Transit commercial cargo van") is True
    assert is_oversized_vehicle("Lifted dually truck") is True
    assert is_oversized_vehicle("Motorhome 30ft") is True


def test_shop_operating_hours_sunday_closed() -> None:
    """Verify shop rejects appointments on Sundays."""
    # 2026-10-11 is a Sunday
    sunday_dt = datetime(2026, 10, 11, 10, 0)
    assert sunday_dt.weekday() == 6
    is_valid, reason = ShopHours.validate_slot_within_hours(sunday_dt, duration_minutes=45)
    assert is_valid is False
    assert "closed on Sundays" in reason


def test_shop_operating_hours_valid_and_buffer() -> None:
    """Verify slot validation against 8 AM - 6 PM operating hours."""
    # Monday 2026-10-12
    # 1. Valid morning slot: 9:00 AM to 10:30 AM (90 mins)
    valid_dt = datetime(2026, 10, 12, 9, 0)
    is_valid, reason = ShopHours.validate_slot_within_hours(valid_dt, duration_minutes=90)
    assert is_valid is True
    assert reason == ""

    # 2. Before open: 7:30 AM
    early_dt = datetime(2026, 10, 12, 7, 30)
    is_valid, reason = ShopHours.validate_slot_within_hours(early_dt, duration_minutes=45)
    assert is_valid is False
    assert "before shop opening" in reason

    # 3. Exactly touches closing: 3:00 PM for 180 min service (ends at 6:00 PM) -> VALID
    on_time_dt = datetime(2026, 10, 12, 15, 0)
    is_valid, reason = ShopHours.validate_slot_within_hours(on_time_dt, duration_minutes=180)
    assert is_valid is True

    # 4. Exceeds closing buffer: 5:00 PM for 90 min service (ends at 6:30 PM) -> INVALID
    over_dt = datetime(2026, 10, 12, 17, 0)
    is_valid, reason = ShopHours.validate_slot_within_hours(over_dt, duration_minutes=90)
    assert is_valid is False
    assert "extends past 6:00 PM closing time" in reason


def test_contact_and_call_log_schemas() -> None:
    """Verify Pydantic models for customer records and call logs."""
    contact = Contact(
        phone_number="+15551234567",
        customer_name="Alice Smith",
        vehicle_type="Tesla Model 3 (Sedan)",
        last_contact_date="2026-10-08",
    )
    assert contact.total_bookings == 1
    assert contact.customer_name == "Alice Smith"

    log = CallLog(
        timestamp="2026-10-08T10:00:00Z",
        caller_phone="+15551234567",
        caller_name="Alice Smith",
        call_intent=CallIntent.BOOKING,
        outcome="Booked Express Wash for 2026-10-12 at 10:00 AM",
        needs_human_followup=False,
        summary="Customer booked standard appointment.",
    )
    assert log.needs_human_followup is False
    assert log.call_intent == CallIntent.BOOKING
