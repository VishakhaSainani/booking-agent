"""Domain models, business rules, and entities for Cedar Lane Auto Detailing.

This module models services, pricing, operating hours, vehicle categories,
and decision boundaries as pure Python types and Pydantic models.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


class VehicleType(StrEnum):
    """Categorization of vehicles serviced by the shop."""

    SEDAN = "Sedan"
    COUPE = "Coupe"
    HATCHBACK = "Hatchback"
    SUV = "SUV"
    CROSSOVER = "Crossover"
    PICKUP_TRUCK = "Pickup Truck"
    PASSENGER_MINIVAN = "Passenger Minivan"
    # Special / Oversized types that require manager review
    COMMERCIAL_CARGO_VAN = "Commercial Cargo Van"
    LIFTED_DUALLY_TRUCK = "Lifted Dually Truck"
    RV = "RV"
    MOTORHOME = "Motorhome"
    BOAT = "Boat"
    HEAVY_MACHINERY = "Heavy Commercial Machinery"
    OTHER_OVERSIZED = "Other Oversized"


OVERSIZED_VEHICLES: set[VehicleType] = {
    VehicleType.COMMERCIAL_CARGO_VAN,
    VehicleType.LIFTED_DUALLY_TRUCK,
    VehicleType.RV,
    VehicleType.MOTORHOME,
    VehicleType.BOAT,
    VehicleType.HEAVY_MACHINERY,
    VehicleType.OTHER_OVERSIZED,
}


def is_oversized_vehicle(vehicle: VehicleType | str) -> bool:
    """Determine whether a vehicle requires a human manager quote due to size."""
    if isinstance(vehicle, VehicleType):
        return vehicle in OVERSIZED_VEHICLES

    normalized = vehicle.strip().lower()
    for oversized in OVERSIZED_VEHICLES:
        if oversized.value.lower() in normalized or normalized in oversized.value.lower():
            return True

    keywords = [
        "cargo van",
        "dually",
        "rv",
        "motorhome",
        "boat",
        "trailer",
        "machinery",
        "heavy",
    ]
    return any(keyword in normalized for keyword in keywords)


class ServiceType(StrEnum):
    """Available detailing services offered by Cedar Lane."""

    EXPRESS_WASH = "Express Wash & Vac"
    INTERIOR_DETAIL = "Interior Detail & Wash"
    FULL_DETAIL = "Full Detail"
    CERAMIC_COATING = "Ceramic Coating / Paint Correction"

    @property
    def duration_minutes(self) -> int:
        """Returns standard duration in minutes."""
        match self:
            case ServiceType.EXPRESS_WASH:
                return 45
            case ServiceType.INTERIOR_DETAIL:
                return 90
            case ServiceType.FULL_DETAIL:
                return 180
            case ServiceType.CERAMIC_COATING:
                return 0  # Multi-day, custom duration requiring quote

    @property
    def requires_human_quote(self) -> bool:
        """Flag indicating if this service requires a manual manager quote."""
        return self == ServiceType.CERAMIC_COATING

    def get_price(self, vehicle: VehicleType | str) -> tuple[int, bool]:
        """Returns (base_price_dollars, is_custom_quote).

        - Express Wash & Vac: $50 (Sedan/Coupe/Hatchback) / $70 (SUV/Truck/Van)
        - Interior Detail: $150 (Sedan/Coupe/Hatchback) / $190 (SUV/Truck/Van)
        - Full Detail: $250 (Sedan/Coupe/Hatchback) / $320 (SUV/Truck/Van)
        - Ceramic Coating: $800+ (Requires human quote)
        """
        if self.requires_human_quote or is_oversized_vehicle(vehicle):
            return 800 if self == ServiceType.CERAMIC_COATING else 0, True

        v_type_str = vehicle.value if isinstance(vehicle, VehicleType) else str(vehicle)
        normalized = v_type_str.lower()
        is_large = any(k in normalized for k in ["suv", "truck", "crossover", "minivan"])

        match self:
            case ServiceType.EXPRESS_WASH:
                return (70, False) if is_large else (50, False)
            case ServiceType.INTERIOR_DETAIL:
                return (190, False) if is_large else (150, False)
            case ServiceType.FULL_DETAIL:
                return (320, False) if is_large else (250, False)
            case ServiceType.CERAMIC_COATING:
                return 800, True


class ShopHours:
    """Operating hours and slot validation rules for Cedar Lane Auto Detailing."""

    OPEN_TIME = time(8, 0)   # 8:00 AM
    CLOSE_TIME = time(18, 0) # 6:00 PM
    CLOSED_WEEKDAYS = {6}    # Sunday is index 6 in Python datetime.weekday()

    @classmethod
    def is_shop_open_on_date(cls, check_date: date) -> bool:
        """Check if shop operates on the given calendar date (Closed Sundays)."""
        return check_date.weekday() not in cls.CLOSED_WEEKDAYS

    @classmethod
    def validate_slot_within_hours(
        cls,
        start_dt: datetime,
        duration_minutes: int,
    ) -> tuple[bool, str]:
        """Validate if a proposed appointment fits within operating hours and closing buffers.

        Returns (is_valid, error_reason).
        """
        if not cls.is_shop_open_on_date(start_dt.date()):
            d_str = start_dt.date().isoformat()
            return False, f"Cedar Lane Auto Detailing is closed on Sundays ({d_str})."

        start_t = start_dt.time()
        if start_t < cls.OPEN_TIME:
            formatted_time = start_t.strftime("%I:%M %p")
            return False, f"Requested start time {formatted_time} is before shop opening (8:00 AM)."

        end_dt = start_dt + timedelta(minutes=duration_minutes)
        # Check if start and end fall on the same day and end time does not exceed closing time
        if end_dt.date() != start_dt.date() or end_dt.time() > cls.CLOSE_TIME:
            formatted_end = end_dt.time().strftime("%I:%M %p")
            return (
                False,
                f"Appointment duration ({duration_minutes} mins) extends past 6:00 PM closing time "
                f"(ends at {formatted_end}).",
            )

        return True, ""


class EscalationReason(StrEnum):
    """Predefined categories requiring human manager intervention."""

    BILLING_DISPUTE = "Billing Dispute / Disputed Charges"
    DAMAGE_CLAIM = "Damage Claim / Liability Issue"
    COMMERCIAL_FLEET = "Commercial Fleet Quote"
    OVERSIZED_VEHICLE = "Oversized / Special Vehicle Review"
    CUSTOM_COATING_QUOTE = "Ceramic Coating / Paint Correction Quote"
    CUSTOMER_REQUEST = "Explicit Customer Manager Request"


PREPARATION_GUIDELINES: list[str] = [
    "Remove all personal belongings, valuables, sunglasses, and important documents.",
    "Clear the trunk and glovebox if an interior detail service is scheduled.",
    (
        "Unbuckle or remove child car seats "
        "(for liability reasons, detailers cannot reinstall child seats)."
    ),
    "Bring vehicle keys/fob and inform staff of any sensitive electronics or aftermarket switches.",
]


class Appointment(BaseModel):
    """Appointment entity stored in Calendar and tracked across conversations."""

    id: str | None = None
    customer_name: str
    phone_number: str
    service_type: ServiceType
    vehicle_type: str
    start_time: datetime
    end_time: datetime
    notes: str = ""
    is_cancelled: bool = False


class Contact(BaseModel):
    """Customer contact record for Google Sheets 'Contacts' tab."""

    phone_number: str = Field(..., description="Primary key / identifier")
    customer_name: str
    vehicle_type: str
    total_bookings: int = 1
    last_contact_date: str
    notes: str = ""


class CallIntent(StrEnum):
    """Categorized customer intent for audit logs."""

    BOOKING = "Booking"
    RESCHEDULE = "Reschedule"
    CANCELLATION = "Cancellation"
    INQUIRY = "Inquiry"
    COMPLAINT = "Complaint"
    RUNNING_LATE = "Running Late"


class CallLog(BaseModel):
    """Audit log entry for Google Sheets 'Call Logs' tab."""

    timestamp: str
    caller_phone: str
    caller_name: str
    call_intent: CallIntent
    outcome: str
    needs_human_followup: bool = False
    summary: str
    vapi_call_id: str | None = None
