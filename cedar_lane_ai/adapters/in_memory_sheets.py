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
        self._contact_counter: int = 0
        self._call_counter: int = 0

    def clear(self) -> None:
        """Clear all in-memory contacts and logs (useful for test resets)."""
        self._contacts.clear()
        self._logs.clear()
        self._contact_counter = 0
        self._call_counter = 0

    def upsert_contact(
        self,
        phone_number: str,
        customer_name: str,
        vehicle_type: str = "",
        notes: str = "",
        is_booking: bool = False,
        email: str = "",
    ) -> Contact:
        """Upsert customer record by phone number."""
        key = normalize_phone(phone_number)
        now_iso = datetime.now().isoformat(timespec="seconds")

        if key in self._contacts:
            existing = self._contacts[key]
            updated_bookings = existing.total_bookings + (1 if is_booking else 0)
            combined_notes = (
                f"{existing.notes}; {notes}".strip("; ") if notes else existing.notes
            )
            updated = existing.model_copy(
                update={
                    "name": customer_name or existing.name,
                    "email": email or existing.email,
                    "vehicle_type": vehicle_type or existing.vehicle_type,
                    "total_bookings": updated_bookings,
                    "updated_at": now_iso,
                    "last_call_at": now_iso,
                    "notes": combined_notes,
                }
            )
            self._contacts[key] = updated
            return updated

        # New customer contact
        self._contact_counter += 1
        cid = f"con_{self._contact_counter:03d}"
        new_contact = Contact(
            contact_id=cid,
            name=customer_name,
            phone=phone_number,
            email=email,
            vehicle_type=vehicle_type,
            notes=notes,
            created_at=now_iso,
            updated_at=now_iso,
            last_call_at=now_iso,
            total_bookings=1 if is_booking else 0,
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
        self._call_counter += 1
        now_iso = datetime.now().isoformat(timespec="seconds")
        cid = log.contact_id
        if not cid and log.phone:
            existing = self.get_contact(log.phone)
            if existing:
                cid = existing.contact_id
            else:
                created = self.upsert_contact(
                    phone_number=log.phone,
                    customer_name="",
                    notes=f"Auto-created from interaction {log.intent}",
                )
                cid = created.contact_id

        call_id = log.call_id or f"call_{self._call_counter:03d}"
        started_at = log.started_at or now_iso
        cname = log.caller_name
        if not cname and log.phone:
            c = self.get_contact(log.phone)
            if c:
                cname = c.name

        prepared_log = log.model_copy(
            update={
                "call_id": call_id,
                "contact_id": cid,
                "caller_name": cname,
                "started_at": started_at,
            }
        )
        self._logs.append(prepared_log)

    def list_call_logs(self, limit: int = 50) -> list[CallLog]:
        """Return the most recent call logs (newest first)."""
        return list(reversed(self._logs[-limit:]))
