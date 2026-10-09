"""Abstract interface for Calendar scheduling adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from cedar_lane_ai.domain import Appointment, ServiceType


class CalendarAdapter(ABC):
    """Abstract base class for Calendar operations (Mock & Google Calendar)."""

    @abstractmethod
    def list_day_events(self, date_str: str) -> list[Appointment]:
        """Retrieve all active appointment events for a target date (YYYY-MM-DD)."""

    @abstractmethod
    def check_slot_availability(
        self,
        date_str: str,
        requested_time_str: str,
        duration_minutes: int,
    ) -> bool:
        """Check if requested time window overlaps any existing event or violates shop hours."""

    @abstractmethod
    def find_alternative_slots(
        self,
        date_str: str,
        requested_time_str: str,
        duration_minutes: int,
        limit: int = 3,
    ) -> list[str]:
        """Calculate the closest available open 30-minute slots if requested slot is busy."""

    @abstractmethod
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
        """Create a new appointment in the calendar."""

    @abstractmethod
    def update_appointment_event(
        self,
        event_id: str,
        new_start_dt: datetime,
        new_end_dt: datetime,
    ) -> Appointment:
        """Reschedule an existing appointment to a new time window."""

    @abstractmethod
    def cancel_appointment_event(self, event_id: str) -> bool:
        """Cancel an appointment event."""

    @abstractmethod
    def find_appointment_by_phone(
        self,
        phone: str,
        date_str: str | None = None,
    ) -> Appointment | None:
        """Find an active appointment for a customer by phone number."""
