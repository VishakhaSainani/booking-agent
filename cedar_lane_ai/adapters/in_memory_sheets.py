"""In-memory simulation of Google Sheets for development, UI sidebar, and tests."""

from __future__ import annotations

from datetime import datetime

from cedar_lane_ai.adapters.sheets_base import SheetsAdapter
from cedar_lane_ai.domain import CallLog, Contact


def normalize_phone(phone: str) -> str:
    """Normalize phone string to uniform 10-digit format for reliable matching."""
    digits = "".join(filter(str.isdigit, phone))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if digits else phone.strip()


class InMemorySheetsAdapter(SheetsAdapter):
    """In-memory thread-safe simulation of Google Sheets Contacts and Call Logs."""

    def __init__(self) -> None:
        self._contacts: dict[str, Contact] = {}
        self._logs: list[CallLog] = []

    def clear(self) -> None:
        """Clear all in-memory contacts and logs (useful for test resets)."""
        self._contacts.clear()
        self._logs.clear()

    def upsert_contact(
        self,
        phone_number: str,
        customer_name: str,
        vehicle_type: str,
        notes: str = "",
        is_booking: bool = False,
    ) -> Contact:
        """Upsert customer record by phone number."""
        key = normalize_phone(phone_number)
        today_str = datetime.now().date().isoformat()

        if key in self._contacts:
            existing = self._contacts[key]
            updated_bookings = existing.total_bookings + (1 if is_booking else 0)
            combined_notes = (
                f"{existing.notes}; {notes}".strip("; ") if notes else existing.notes
            )
            updated = existing.model_copy(
                update={
                    "customer_name": customer_name or existing.customer_name,
                    "vehicle_type": vehicle_type or existing.vehicle_type,
                    "total_bookings": updated_bookings,
                    "last_contact_date": today_str,
                    "notes": combined_notes,
                }
            )
            self._contacts[key] = updated
            return updated

        # New customer contact
        new_contact = Contact(
            phone_number=phone_number,
            customer_name=customer_name,
            vehicle_type=vehicle_type,
            total_bookings=1 if is_booking else 0,
            last_contact_date=today_str,
            notes=notes,
        )
        self._contacts[key] = new_contact
        return new_contact

    def get_contact(self, phone_number: str) -> Contact | None:
        """Retrieve customer record by phone number."""
        key = normalize_phone(phone_number)
        return self._contacts.get(key)

    def list_contacts(self) -> list[Contact]:
        """Return all recorded contacts."""
        return list(self._contacts.values())

    def append_call_log(self, log: CallLog) -> None:
        """Append an interaction or audit log entry."""
        self._logs.append(log)

    def list_call_logs(self, limit: int = 50) -> list[CallLog]:
        """Return the most recent call logs (newest first)."""
        return list(reversed(self._logs[-limit:]))
