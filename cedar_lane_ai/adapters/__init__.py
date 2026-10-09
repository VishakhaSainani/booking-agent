"""Adapters layer exporting Calendar and Sheets clients and factories."""

from __future__ import annotations

import logging

from cedar_lane_ai.adapters.calendar_base import CalendarAdapter
from cedar_lane_ai.adapters.google_calendar import GoogleCalendarAdapter
from cedar_lane_ai.adapters.in_memory_calendar import (
    InMemoryCalendarAdapter,
    parse_date_string,
    parse_time_string,
)
from cedar_lane_ai.config import settings

logger = logging.getLogger(__name__)

_CALENDAR_SINGLETON: CalendarAdapter | None = None


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
        _CALENDAR_SINGLETON = GoogleCalendarAdapter()
        return _CALENDAR_SINGLETON
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to initialize GoogleCalendarAdapter (%s). "
            "Falling back to InMemoryCalendarAdapter.",
            exc,
        )
        _CALENDAR_SINGLETON = InMemoryCalendarAdapter()
        return _CALENDAR_SINGLETON


__all__ = [
    "CalendarAdapter",
    "GoogleCalendarAdapter",
    "InMemoryCalendarAdapter",
    "get_calendar_adapter",
    "parse_date_string",
    "parse_time_string",
]
