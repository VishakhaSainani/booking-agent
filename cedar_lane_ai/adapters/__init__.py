"""Adapters layer exporting Calendar and Sheets clients and factories."""

from __future__ import annotations

import logging

from cedar_lane_ai.adapters.calendar_base import CalendarAdapter
from cedar_lane_ai.adapters.google_calendar import GoogleCalendarAdapter
from cedar_lane_ai.adapters.google_sheets import GoogleSheetsAdapter
from cedar_lane_ai.adapters.in_memory_calendar import (
    InMemoryCalendarAdapter,
    parse_date_string,
    parse_time_string,
)
from cedar_lane_ai.adapters.in_memory_sheets import InMemorySheetsAdapter, normalize_phone
from cedar_lane_ai.adapters.sheets_base import SheetsAdapter
from cedar_lane_ai.config import settings

logger = logging.getLogger(__name__)

_CALENDAR_SINGLETON: CalendarAdapter | None = None
_SHEETS_SINGLETON: SheetsAdapter | None = None


def get_calendar_adapter(force_fresh: bool = False) -> CalendarAdapter:
    """Return configured calendar adapter (Mock or Google Calendar)."""
    global _CALENDAR_SINGLETON

    if _CALENDAR_SINGLETON is not None and not force_fresh:
        return _CALENDAR_SINGLETON

    if settings.use_mock_integrations:
        logger.info("Using InMemoryCalendarAdapter (USE_MOCK_INTEGRATIONS is True)")
        _CALENDAR_SINGLETON = InMemoryCalendarAdapter()
        return _CALENDAR_SINGLETON

    try:
        logger.info("Attempting to initialize GoogleCalendarAdapter...")
        adapter = GoogleCalendarAdapter()
        adapter.service.events().list(calendarId=adapter.calendar_id, maxResults=1).execute()
        _CALENDAR_SINGLETON = adapter
        return _CALENDAR_SINGLETON
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to initialize GoogleCalendarAdapter (%s). "
            "Falling back to InMemoryCalendarAdapter.",
            exc,
        )
        _CALENDAR_SINGLETON = InMemoryCalendarAdapter()
        return _CALENDAR_SINGLETON


def get_sheets_adapter(force_fresh: bool = False) -> SheetsAdapter:
    """Return configured sheets adapter (Mock or Google Sheets)."""
    global _SHEETS_SINGLETON

    if _SHEETS_SINGLETON is not None and not force_fresh:
        return _SHEETS_SINGLETON

    if settings.use_mock_integrations:
        logger.info("Using InMemorySheetsAdapter (USE_MOCK_INTEGRATIONS is True)")
        _SHEETS_SINGLETON = InMemorySheetsAdapter()
        return _SHEETS_SINGLETON

    try:
        logger.info("Attempting to initialize GoogleSheetsAdapter...")
        _SHEETS_SINGLETON = GoogleSheetsAdapter()
        return _SHEETS_SINGLETON
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to initialize GoogleSheetsAdapter (%s). "
            "Falling back to InMemorySheetsAdapter.",
            exc,
        )
        _SHEETS_SINGLETON = InMemorySheetsAdapter()
        return _SHEETS_SINGLETON


__all__ = [
    "CalendarAdapter",
    "GoogleCalendarAdapter",
    "GoogleSheetsAdapter",
    "InMemoryCalendarAdapter",
    "InMemorySheetsAdapter",
    "SheetsAdapter",
    "get_calendar_adapter",
    "get_sheets_adapter",
    "normalize_phone",
    "parse_date_string",
    "parse_time_string",
]
