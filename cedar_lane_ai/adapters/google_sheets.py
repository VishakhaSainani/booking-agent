"""Live Google Sheets Adapter using Google Service Account credentials."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from cedar_lane_ai.adapters.in_memory_sheets import normalize_phone
from cedar_lane_ai.adapters.sheets_base import SheetsAdapter
from cedar_lane_ai.config import settings
from cedar_lane_ai.domain import CallIntent, CallLog, Contact

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CONTACTS_HEADER = [
    "Phone Number",
    "Customer Name",
    "Vehicle Type",
    "Total Bookings",
    "Last Contact Date",
    "Notes / Preferences",
]

CALL_LOGS_HEADER = [
    "Timestamp",
    "Caller Phone",
    "Caller Name",
    "Call Intent",
    "Outcome / Action Taken",
    "Needs Human Follow-up?",
    "Summary",
    "Vapi Call ID",
]


class GoogleSheetsAdapter(SheetsAdapter):
    """Google Sheets client maintaining Contacts and Call Logs tabs."""

    def __init__(
        self,
        credentials_file: Path | str | None = None,
        spreadsheet_id: str | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or settings.google_sheets_spreadsheet_id
        cred_path = Path(credentials_file or settings.google_service_account_file)

        if not cred_path.exists():
            raise FileNotFoundError(
                f"Google service account credentials file not found at: {cred_path.resolve()}"
            )

        credentials = service_account.Credentials.from_service_account_file(
            str(cred_path),
            scopes=SCOPES,
        )
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self._ensure_tab_headers()

    def _ensure_tab_headers(self) -> None:
        """Verify or create headers for Contacts and Call Logs tabs."""
        try:
            # Check Contacts tab
            res_c = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A1:F1")
                .execute()
            )
            if not res_c.get("values"):
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Contacts!A1:F1",
                    valueInputOption="RAW",
                    body={"values": [CONTACTS_HEADER]},
                ).execute()

            # Check Call Logs tab
            res_l = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range="Call Logs!A1:H1")
                .execute()
            )
            if not res_l.get("values"):
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Call Logs!A1:H1",
                    valueInputOption="RAW",
                    body={"values": [CALL_LOGS_HEADER]},
                ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not auto-verify sheet tab headers: %s", exc)

    def upsert_contact(
        self,
        phone_number: str,
        customer_name: str,
        vehicle_type: str,
        notes: str = "",
        is_booking: bool = False,
    ) -> Contact:
        """Upsert row in the Contacts tab by matching phone number."""
        target_norm = normalize_phone(phone_number)
        today_str = datetime.now().date().isoformat()

        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:F")
            .execute()
        )
        rows: list[list[Any]] = res.get("values", [])

        # Check existing row
        for idx, row in enumerate(rows[1:], start=2):  # 1-indexed, row 1 is header
            if row and normalize_phone(str(row[0])) == target_norm:
                existing_bookings = int(row[3]) if len(row) > 3 and str(row[3]).isdigit() else 0
                updated_bookings = existing_bookings + (1 if is_booking else 0)
                existing_notes = str(row[5]) if len(row) > 5 else ""
                combined_notes = (
                    f"{existing_notes}; {notes}".strip("; ") if notes else existing_notes
                )

                updated_row = [
                    phone_number,
                    customer_name or (row[1] if len(row) > 1 else ""),
                    vehicle_type or (row[2] if len(row) > 2 else ""),
                    updated_bookings,
                    today_str,
                    combined_notes,
                ]

                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"Contacts!A{idx}:F{idx}",
                    valueInputOption="RAW",
                    body={"values": [updated_row]},
                ).execute()

                return Contact(
                    phone_number=phone_number,
                    customer_name=str(updated_row[1]),
                    vehicle_type=str(updated_row[2]),
                    total_bookings=updated_bookings,
                    last_contact_date=today_str,
                    notes=combined_notes,
                )

        # Append new row
        new_row = [
            phone_number,
            customer_name,
            vehicle_type,
            1 if is_booking else 0,
            today_str,
            notes,
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Contacts!A:F",
            valueInputOption="RAW",
            body={"values": [new_row]},
        ).execute()

        return Contact(
            phone_number=phone_number,
            customer_name=customer_name,
            vehicle_type=vehicle_type,
            total_bookings=1 if is_booking else 0,
            last_contact_date=today_str,
            notes=notes,
        )

    def get_contact(self, phone_number: str) -> Contact | None:
        """Fetch contact matching phone number."""
        target_norm = normalize_phone(phone_number)
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:F")
            .execute()
        )
        rows: list[list[Any]] = res.get("values", [])
        for row in rows[1:]:
            if row and normalize_phone(str(row[0])) == target_norm:
                return Contact(
                    phone_number=str(row[0]),
                    customer_name=str(row[1]) if len(row) > 1 else "",
                    vehicle_type=str(row[2]) if len(row) > 2 else "",
                    total_bookings=int(row[3]) if len(row) > 3 and str(row[3]).isdigit() else 0,
                    last_contact_date=str(row[4]) if len(row) > 4 else "",
                    notes=str(row[5]) if len(row) > 5 else "",
                )
        return None

    def list_contacts(self) -> list[Contact]:
        """Fetch all contacts from sheet."""
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:F")
            .execute()
        )
        contacts: list[Contact] = []
        for row in res.get("values", [])[1:]:
            if row:
                contacts.append(
                    Contact(
                        phone_number=str(row[0]),
                        customer_name=str(row[1]) if len(row) > 1 else "",
                        vehicle_type=str(row[2]) if len(row) > 2 else "",
                        total_bookings=int(row[3]) if len(row) > 3 and str(row[3]).isdigit() else 0,
                        last_contact_date=str(row[4]) if len(row) > 4 else "",
                        notes=str(row[5]) if len(row) > 5 else "",
                    )
                )
        return contacts

    def append_call_log(self, log: CallLog) -> None:
        """Append log entry to Call Logs tab."""
        row = [
            log.timestamp,
            log.caller_phone,
            log.caller_name,
            log.call_intent.value,
            log.outcome,
            "YES" if log.needs_human_followup else "NO",
            log.summary,
            log.vapi_call_id or "",
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Call Logs!A:H",
            valueInputOption="RAW",
            body={"values": [row]},
        ).execute()

    def list_call_logs(self, limit: int = 50) -> list[CallLog]:
        """Fetch latest call logs from sheet."""
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Call Logs!A:H")
            .execute()
        )
        logs: list[CallLog] = []
        for row in res.get("values", [])[1:]:
            if not row:
                continue
            logs.append(
                CallLog(
                    timestamp=str(row[0]),
                    caller_phone=str(row[1]) if len(row) > 1 else "",
                    caller_name=str(row[2]) if len(row) > 2 else "",
                    call_intent=CallIntent(row[3]) if len(row) > 3 else CallIntent.INQUIRY,
                    outcome=str(row[4]) if len(row) > 4 else "",
                    needs_human_followup=(str(row[5]).upper() == "YES") if len(row) > 5 else False,
                    summary=str(row[6]) if len(row) > 6 else "",
                    vapi_call_id=str(row[7]) if len(row) > 7 and row[7] else None,
                )
            )
        return list(reversed(logs[-limit:]))
