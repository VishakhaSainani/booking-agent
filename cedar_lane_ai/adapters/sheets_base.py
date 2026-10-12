"""Abstract interface for Google Sheets customer directory and call logs."""

from __future__ import annotations

from abc import ABC, abstractmethod

from cedar_lane_ai.domain import CallLog, Contact


class SheetsAdapter(ABC):
    """Abstract base class for persistent customer records and audit trails."""

    @abstractmethod
    def upsert_contact(
        self,
        phone_number: str,
        customer_name: str,
        vehicle_type: str = "",
        notes: str = "",
        is_booking: bool = False,
        email: str = "",
    ) -> Contact:
        """Upsert customer record.

        If contact exists:
          - Updates name/email/vehicle/notes if provided
          - Updates last_call_at to current timestamp
          - Increments total_bookings if is_booking is True
        If contact does not exist:
          - Inserts new row with contact_id, created_at, updated_at, last_call_at.
        """

    @abstractmethod
    def get_contact(self, phone_number: str) -> Contact | None:
        """Lookup customer by phone number."""

    @abstractmethod
    def list_contacts(self) -> list[Contact]:
        """Return all recorded contacts."""

    @abstractmethod
    def append_call_log(self, log: CallLog) -> None:
        """Append an interaction or audit log entry."""

    @abstractmethod
    def list_call_logs(self, limit: int = 50) -> list[CallLog]:
        """Return the most recent call log entries."""
