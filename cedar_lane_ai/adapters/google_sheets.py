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
from cedar_lane_ai.domain import CallLog, Contact

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CONTACTS_HEADER = [
    "contact_id",
    "name",
    "phone",
    "email",
    "notes",
    "created_at",
    "updated_at",
    "last_call_at",
]

CALL_LOGS_HEADER = [
    "call_id",
    "contact_id",
    "phone",
    "started_at",
    "channel",
    "intent",
    "summary",
    "outcome",
    "appointment_id",
    "handoff_required",
    "handoff_reason",
    "status",
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
                .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A1:H1")
                .execute()
            )
            vals_c = res_c.get("values", [])
            if not vals_c or vals_c[0] != CONTACTS_HEADER:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Contacts!A1:H1",
                    valueInputOption="RAW",
                    body={"values": [CONTACTS_HEADER]},
                ).execute()

            # Check Call Logs tab
            res_l = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range="Call Logs!A1:L1")
                .execute()
            )
            vals_l = res_l.get("values", [])
            if not vals_l or vals_l[0] != CALL_LOGS_HEADER:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range="Call Logs!A1:L1",
                    valueInputOption="RAW",
                    body={"values": [CALL_LOGS_HEADER]},
                ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not auto-verify sheet tab headers: %s", exc)

    def upsert_contact(
        self,
        phone_number: str,
        customer_name: str,
        vehicle_type: str = "",
        notes: str = "",
        is_booking: bool = False,
        email: str = "",
    ) -> Contact:
        """Upsert row in the Contacts tab by matching phone number."""
        target_norm = normalize_phone(phone_number)
        now_iso = datetime.now().isoformat(timespec="seconds")

        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:H")
            .execute()
        )
        rows: list[list[Any]] = res.get("values", [])

        # Check existing row (row 1 is header)
        for idx, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            # Check phone in column C (index 2) or fallback to column A (index 0)
            row_phone = str(row[2]) if len(row) > 2 else str(row[0])
            if normalize_phone(row_phone) == target_norm:
                is_con = len(row) > 0 and str(row[0]).startswith("con_")
                cid = str(row[0]) if is_con else f"con_{idx:03d}"
                existing_notes = str(row[4]) if len(row) > 4 else ""
                combined_notes = (
                    f"{existing_notes}; {notes}".strip("; ") if notes else existing_notes
                )
                created_at = str(row[5]) if len(row) > 5 else now_iso
                existing_email = str(row[3]) if len(row) > 3 else ""

                updated_row = [
                    cid,
                    customer_name or (str(row[1]) if len(row) > 1 else ""),
                    phone_number,
                    email or existing_email,
                    combined_notes,
                    created_at,
                    now_iso,
                    now_iso,
                ]

                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"Contacts!A{idx}:H{idx}",
                    valueInputOption="RAW",
                    body={"values": [updated_row]},
                ).execute()

                return Contact(
                    contact_id=cid,
                    name=str(updated_row[1]),
                    phone=phone_number,
                    email=str(updated_row[3]),
                    notes=combined_notes,
                    created_at=created_at,
                    updated_at=now_iso,
                    last_call_at=now_iso,
                    vehicle_type=vehicle_type,
                    total_bookings=1 if is_booking else 0,
                )

        # Append new row
        cid = f"con_{len(rows):03d}"
        new_row = [
            cid,
            customer_name,
            phone_number,
            email,
            notes,
            now_iso,
            now_iso,
            now_iso,
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Contacts!A:H",
            valueInputOption="RAW",
            body={"values": [new_row]},
        ).execute()

        return Contact(
            contact_id=cid,
            name=customer_name,
            phone=phone_number,
            email=email,
            notes=notes,
            created_at=now_iso,
            updated_at=now_iso,
            last_call_at=now_iso,
            vehicle_type=vehicle_type,
            total_bookings=1 if is_booking else 0,
        )

    def get_contact(self, phone_number: str) -> Contact | None:
        """Fetch contact matching phone number."""
        target_norm = normalize_phone(phone_number)
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:H")
            .execute()
        )
        rows: list[list[Any]] = res.get("values", [])
        for row in rows[1:]:
            if not row:
                continue
            row_phone = str(row[2]) if len(row) > 2 else str(row[0])
            if normalize_phone(row_phone) == target_norm:
                return Contact(
                    contact_id=str(row[0]) if len(row) > 0 else "",
                    name=str(row[1]) if len(row) > 1 else "",
                    phone=str(row[2]) if len(row) > 2 else str(row[0]),
                    email=str(row[3]) if len(row) > 3 else "",
                    notes=str(row[4]) if len(row) > 4 else "",
                    created_at=str(row[5]) if len(row) > 5 else "",
                    updated_at=str(row[6]) if len(row) > 6 else "",
                    last_call_at=str(row[7]) if len(row) > 7 else "",
                )
        return None

    def list_contacts(self) -> list[Contact]:
        """Fetch all contacts from sheet."""
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Contacts!A:H")
            .execute()
        )
        contacts: list[Contact] = []
        for row in res.get("values", [])[1:]:
            if not row:
                continue
            contacts.append(
                Contact(
                    contact_id=str(row[0]) if len(row) > 0 else "",
                    name=str(row[1]) if len(row) > 1 else "",
                    phone=str(row[2]) if len(row) > 2 else str(row[0]),
                    email=str(row[3]) if len(row) > 3 else "",
                    notes=str(row[4]) if len(row) > 4 else "",
                    created_at=str(row[5]) if len(row) > 5 else "",
                    updated_at=str(row[6]) if len(row) > 6 else "",
                    last_call_at=str(row[7]) if len(row) > 7 else "",
                )
            )
        return contacts

    def append_call_log(self, log: CallLog) -> None:
        """Append log entry to Call Logs tab."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        call_id = log.call_id or f"call_{datetime.now().strftime('%y%m%d%H%M%S')}"
        started_at = log.started_at or now_iso

        # Ensure contact_id is linked
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

        row = [
            call_id,
            cid,
            log.phone,
            started_at,
            log.channel,
            log.intent,
            log.summary,
            log.outcome,
            log.appointment_id or "",
            "TRUE" if log.handoff_required else "FALSE",
            log.handoff_reason,
            log.status,
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Call Logs!A:L",
            valueInputOption="RAW",
            body={"values": [row]},
        ).execute()

    def list_call_logs(self, limit: int = 50) -> list[CallLog]:
        """Fetch latest call logs from sheet."""
        res = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range="Call Logs!A:L")
            .execute()
        )
        logs: list[CallLog] = []
        for row in res.get("values", [])[1:]:
            if not row:
                continue
            logs.append(
                CallLog(
                    call_id=str(row[0]) if len(row) > 0 else "",
                    contact_id=str(row[1]) if len(row) > 1 else "",
                    phone=str(row[2]) if len(row) > 2 else "",
                    started_at=str(row[3]) if len(row) > 3 else "",
                    channel=str(row[4]) if len(row) > 4 else "chat",
                    intent=str(row[5]) if len(row) > 5 else "Inquiry",
                    summary=str(row[6]) if len(row) > 6 else "",
                    outcome=str(row[7]) if len(row) > 7 else "",
                    appointment_id=str(row[8]) if len(row) > 8 and row[8] else None,
                    handoff_required=(
                        (str(row[9]).upper() in ("TRUE", "YES")) if len(row) > 9 else False
                    ),
                    handoff_reason=str(row[10]) if len(row) > 10 else "",
                    status=str(row[11]) if len(row) > 11 else "completed",
                )
            )
        return list(reversed(logs[-limit:]))
