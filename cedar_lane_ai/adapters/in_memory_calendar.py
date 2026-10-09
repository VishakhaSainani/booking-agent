"""In-memory Calendar Adapter for development, automated testing, and offline use."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from cedar_lane_ai.adapters.calendar_base import CalendarAdapter
from cedar_lane_ai.domain import Appointment, ServiceType, ShopHours


def parse_time_string(time_str: str) -> time:
    """Robustly parse 12-hour (e.g., '3:30 PM') or 24-hour (e.g., '15:30') time strings."""
    time_str = time_str.strip()
    formats = [
        "%H:%M",
        "%H:%M:%S",
        "%I:%M %p",
        "%I:%M%p",
        "%I %p",
        "%I%p",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse time string: '{time_str}'")


def parse_date_string(date_str: str) -> date:
    """Robustly parse date strings (e.g., '2026-10-15')."""
    date_str = date_str.strip()
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date string: '{date_str}'")


class InMemoryCalendarAdapter(CalendarAdapter):
    """In-memory thread-safe simulation of Google Calendar."""

    def __init__(self) -> None:
        self._events: dict[str, Appointment] = {}

    def clear(self) -> None:
        """Clear all stored calendar events (useful for test resets)."""
        self._events.clear()

    def list_day_events(self, date_str: str) -> list[Appointment]:
        """Retrieve active appointments for target date."""
        target_date = parse_date_string(date_str)
        return [
            apt
            for apt in self._events.values()
            if not apt.is_cancelled and apt.start_time.date() == target_date
        ]

    def check_slot_availability(
        self,
        date_str: str,
        requested_time_str: str,
        duration_minutes: int,
    ) -> bool:
        """Check if requested time window is free from collisions and within shop hours."""
        target_date = parse_date_string(date_str)
        target_time = parse_time_string(requested_time_str)
        start_dt = datetime.combine(target_date, target_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        is_valid_hours, _ = ShopHours.validate_slot_within_hours(start_dt, duration_minutes)
        if not is_valid_hours:
            return False

        # Check collision with existing active events
        for apt in self.list_day_events(date_str):
            if start_dt < apt.end_time and end_dt > apt.start_time:
                return False

        return True

    def find_alternative_slots(
        self,
        date_str: str,
        requested_time_str: str,
        duration_minutes: int,
        limit: int = 3,
    ) -> list[str]:
        """Find the closest open 30-minute slots to the requested time."""
        target_date = parse_date_string(date_str)
        requested_time = parse_time_string(requested_time_str)
        requested_dt = datetime.combine(target_date, requested_time)

        if not ShopHours.is_shop_open_on_date(target_date):
            return []

        # Generate candidates every 30 minutes from 8:00 AM to 5:30 PM
        candidate_slots: list[datetime] = []
        curr_dt = datetime.combine(target_date, ShopHours.OPEN_TIME)
        closing_dt = datetime.combine(target_date, ShopHours.CLOSE_TIME)

        while curr_dt + timedelta(minutes=duration_minutes) <= closing_dt:
            # Check availability for this candidate
            c_time_str = curr_dt.strftime("%H:%M")
            if self.check_slot_availability(date_str, c_time_str, duration_minutes):
                candidate_slots.append(curr_dt)
            curr_dt += timedelta(minutes=30)

        # Exclude exact requested datetime if present
        valid_candidates = [
            dt for dt in candidate_slots if dt != requested_dt
        ]

        # Rank candidates by proximity to requested datetime
        valid_candidates.sort(
            key=lambda dt: abs((dt - requested_dt).total_seconds())
        )

        return [dt.strftime("%I:%M %p") for dt in valid_candidates[:limit]]

    def create_appointment_event(
        self,
        customer_name: str,
        phone: str,
        service: ServiceType,
        vehicle_type: str,
        start_dt: datetime,
        end_dt: datetime,
        notes: str = "",
    ) -> Appointment:
        """Create a new appointment in the in-memory store."""
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        appointment = Appointment(
            id=event_id,
            customer_name=customer_name,
            phone_number=phone,
            service_type=service,
            vehicle_type=vehicle_type,
            start_time=start_dt,
            end_time=end_dt,
            notes=notes,
            is_cancelled=False,
        )
        self._events[event_id] = appointment
        return appointment

    def update_appointment_event(
        self,
        event_id: str,
        new_start_dt: datetime,
        new_end_dt: datetime,
    ) -> Appointment:
        """Reschedule an existing appointment."""
        if event_id not in self._events:
            raise KeyError(f"Appointment with id '{event_id}' not found.")
        apt = self._events[event_id]
        updated = apt.model_copy(
            update={"start_time": new_start_dt, "end_time": new_end_dt}
        )
        self._events[event_id] = updated
        return updated

    def cancel_appointment_event(self, event_id: str) -> bool:
        """Cancel an appointment event."""
        if event_id not in self._events:
            return False
        apt = self._events[event_id]
        self._events[event_id] = apt.model_copy(update={"is_cancelled": True})
        return True

    def find_appointment_by_phone(
        self,
        phone: str,
        date_str: str | None = None,
    ) -> Appointment | None:
        """Find active appointment matching customer phone."""
        clean_target = "".join(filter(str.isdigit, phone))
        for apt in self._events.values():
            if apt.is_cancelled:
                continue
            clean_apt_phone = "".join(filter(str.isdigit, apt.phone_number))
            matches = clean_target and (
                clean_target in clean_apt_phone or clean_apt_phone in clean_target
            )
            if matches:
                if date_str:
                    target_date = parse_date_string(date_str)
                    if apt.start_time.date() != target_date:
                        continue
                return apt
        return None
