"""Live Google Calendar Adapter using Google Service Account credentials."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from cedar_lane_ai.adapters.calendar_base import CalendarAdapter
from cedar_lane_ai.adapters.in_memory_calendar import (
    parse_date_string,
    parse_time_string,
)
from cedar_lane_ai.config import settings
from cedar_lane_ai.domain import (
    PREPARATION_GUIDELINES,
    Appointment,
    ServiceType,
    ShopHours,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarAdapter(CalendarAdapter):
    """Google Calendar client managing events via Google Calendar REST API."""

    def __init__(
        self,
        credentials_file: Path | str | None = None,
        calendar_id: str | None = None,
    ) -> None:
        self.calendar_id = calendar_id or settings.google_calendar_id
        cred_path = Path(credentials_file or settings.google_service_account_file)

        if not cred_path.exists():
            raise FileNotFoundError(
                f"Google service account credentials file not found at: {cred_path.resolve()}"
            )

        credentials = service_account.Credentials.from_service_account_file(
            str(cred_path),
            scopes=SCOPES,
        )
        self.service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def list_day_events(self, date_str: str) -> list[Appointment]:
        """Fetch all calendar events for the specified date."""
        target_date = parse_date_string(date_str)
        time_min = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
        time_max = datetime.combine(target_date, datetime.max.time()).isoformat() + "Z"

        events_result = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        items: list[dict[str, Any]] = events_result.get("items", [])
        appointments: list[Appointment] = []

        for item in items:
            summary = item.get("summary", "")
            if "[CANCELLED]" in summary:
                continue

            start_raw = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end_raw = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            if not start_raw or not end_raw:
                continue

            # Strip timezone suffix for naive datetime comparison
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).replace(tzinfo=None)

            appointments.append(
                Appointment(
                    id=item.get("id"),
                    customer_name=summary,
                    phone_number="",
                    service_type=ServiceType.EXPRESS_WASH,
                    vehicle_type="Standard",
                    start_time=start_dt,
                    end_time=end_dt,
                    notes=item.get("description", ""),
                    is_cancelled=False,
                )
            )

        return appointments

    def check_slot_availability(
        self,
        date_str: str,
        requested_time_str: str,
        duration_minutes: int,
    ) -> bool:
        """Check if slot is within business hours and not overlapping with existing events."""
        target_date = parse_date_string(date_str)
        target_time = parse_time_string(requested_time_str)
        start_dt = datetime.combine(target_date, target_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        is_valid_hours, _ = ShopHours.validate_slot_within_hours(start_dt, duration_minutes)
        if not is_valid_hours:
            return False

        existing_events = self.list_day_events(date_str)
        for apt in existing_events:
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
        """Suggest nearest open slots if requested slot is unavailable."""
        target_date = parse_date_string(date_str)
        requested_time = parse_time_string(requested_time_str)
        requested_dt = datetime.combine(target_date, requested_time)

        if not ShopHours.is_shop_open_on_date(target_date):
            return []

        existing_events = self.list_day_events(date_str)
        candidate_slots: list[datetime] = []
        curr_dt = datetime.combine(target_date, ShopHours.OPEN_TIME)
        closing_dt = datetime.combine(target_date, ShopHours.CLOSE_TIME)

        while curr_dt + timedelta(minutes=duration_minutes) <= closing_dt:
            end_candidate = curr_dt + timedelta(minutes=duration_minutes)
            overlap = any(
                curr_dt < apt.end_time and end_candidate > apt.start_time
                for apt in existing_events
            )
            if not overlap and curr_dt != requested_dt:
                candidate_slots.append(curr_dt)
            curr_dt += timedelta(minutes=30)

        candidate_slots.sort(key=lambda dt: abs((dt - requested_dt).total_seconds()))
        return [dt.strftime("%I:%M %p") for dt in candidate_slots[:limit]]

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
        """Create calendar event according to shop specification."""
        prep_bullets = "\n".join(f"- {rule}" for rule in PREPARATION_GUIDELINES)
        description = (
            f"Customer Phone: {phone}\n"
            f"Vehicle Model: {vehicle_type}\n"
            f"Service: {service.value}\n"
            f"Notes: {notes}\n\n"
            f"Preparation Guidelines:\n{prep_bullets}"
        )
        body = {
            "summary": f"[Detailing] {customer_name} - {service.value}",
            "description": description,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
        created = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return Appointment(
            id=created.get("id"),
            customer_name=customer_name,
            phone_number=phone,
            service_type=service,
            vehicle_type=vehicle_type,
            start_time=start_dt,
            end_time=end_dt,
            notes=notes,
            is_cancelled=False,
        )

    def update_appointment_event(
        self,
        event_id: str,
        new_start_dt: datetime,
        new_end_dt: datetime,
    ) -> Appointment:
        """Reschedule existing appointment in Google Calendar."""
        event = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        event["start"] = {"dateTime": new_start_dt.isoformat()}
        event["end"] = {"dateTime": new_end_dt.isoformat()}
        updated = (
            self.service.events()
            .update(calendarId=self.calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return Appointment(
            id=updated.get("id"),
            customer_name=updated.get("summary", ""),
            phone_number="",
            service_type=ServiceType.EXPRESS_WASH,
            vehicle_type="Standard",
            start_time=new_start_dt,
            end_time=new_end_dt,
            is_cancelled=False,
        )

    def cancel_appointment_event(self, event_id: str) -> bool:
        """Cancel an appointment event by marking it [CANCELLED]."""
        try:
            event = (
                self.service.events()
                .get(calendarId=self.calendar_id, eventId=event_id)
                .execute()
            )
            event["summary"] = f"[CANCELLED] {event.get('summary', '')}"
            self.service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event,
            ).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to cancel Google Calendar event %s: %s", event_id, exc)
            return False

    def find_appointment_by_phone(
        self,
        phone: str,
        date_str: str | None = None,
    ) -> Appointment | None:
        """Find event in Google Calendar containing caller phone in description."""
        events_result = (
            self.service.events()
            .list(calendarId=self.calendar_id, q=phone, maxResults=10)
            .execute()
        )
        items = events_result.get("items", [])
        for item in items:
            if "[CANCELLED]" in item.get("summary", ""):
                continue
            start_raw = item.get("start", {}).get("dateTime")
            end_raw = item.get("end", {}).get("dateTime")
            if not start_raw or not end_raw:
                continue
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            if date_str:
                target_date = parse_date_string(date_str)
                if start_dt.date() != target_date:
                    continue
            return Appointment(
                id=item.get("id"),
                customer_name=item.get("summary", ""),
                phone_number=phone,
                service_type=ServiceType.EXPRESS_WASH,
                vehicle_type="Standard",
                start_time=start_dt,
                end_time=end_dt,
                notes=item.get("description", ""),
                is_cancelled=False,
            )
        return None
