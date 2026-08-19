"""
Utility functions for the City of Mishawaka Events Scraper.
"""

import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .parsers import (
        clean_text,
        parse_date_range_or_single,
        parse_iso_datetime,
        parse_time_range,
        parse_weekday_pattern,
        strip_time_expressions,
    )
except ImportError:
    from parsers import (
        clean_text,
        parse_date_range_or_single,
        parse_iso_datetime,
        parse_time_range,
        parse_weekday_pattern,
        strip_time_expressions,
    )

logger = logging.getLogger("MishawakaScraper")


def format_location_address(venue: str, address: str, city_state_zip: str) -> str:
    """Format structured venue and address patterns into 'Venue | Address | City, State ZIP'."""
    parts = []
    if venue:
        parts.append(venue.strip())
    if address:
        parts.append(address.strip())
    if city_state_zip:
        parts.append(city_state_zip.strip())

    return " | ".join(parts) if parts else ""


def expand_event_schedules(
    iso_start_str: Optional[str] = None,
    iso_end_str: Optional[str] = None,
    raw_date_str: str = "",
    raw_time_str: str = "",
    raw_recur_str: str = "",
    upcoming_dates: Optional[List[str]] = None,
    overview_text: str = "",
    base_date: Optional[datetime.date] = None,
) -> List[Dict[str, Any]]:
    """Intelligently parse dates, ISO timestamps, weekday recurrences, and generate individual schedule instances."""
    if base_date is None:
        base_date = datetime.date.today()

    expanded_instances: List[Dict[str, Any]] = []
    seen_keys: Set[Tuple[str, Optional[str], Optional[str]]] = set()

    # 1. Primary: Direct ISO 8601 timestamps from Schema.org JSON-LD
    if iso_start_str:
        start_date, start_time = parse_iso_datetime(iso_start_str)
        end_date, end_time = parse_iso_datetime(iso_end_str) if iso_end_str else (None, None)

        if start_date:
            all_day = start_time is None

            # Check if this is a single day or multi-day span without explicit upcoming dates
            if end_date and end_date > start_date and not upcoming_dates:
                # If end_date is the next day and end_time is midnight (00:00), treat as single day all-day event
                if (end_date - start_date).days == 1 and end_time == datetime.time(0, 0):
                    key = (start_date.isoformat(), None, None)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        expanded_instances.append({
                            "date": start_date.isoformat(),
                            "start_time": None,
                            "end_time": None,
                            "all_day": True,
                        })
                else:
                    day_count = (end_date - start_date).days + 1
                    weekday_pattern = parse_weekday_pattern(raw_recur_str) or parse_weekday_pattern(overview_text)
                    for i in range(min(day_count, 366)):
                        day = start_date + datetime.timedelta(days=i)
                        if weekday_pattern is not None and day.weekday() not in weekday_pattern:
                            continue
                        key = (
                            day.isoformat(),
                            start_time.strftime("%H:%M:%S") if start_time else None,
                            end_time.strftime("%H:%M:%S") if end_time else None,
                        )
                        if key not in seen_keys:
                            seen_keys.add(key)
                            expanded_instances.append({
                                "date": day.isoformat(),
                                "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
                                "end_time": end_time.strftime("%H:%M:%S") if end_time else None,
                                "all_day": all_day,
                            })
            else:
                key = (
                    start_date.isoformat(),
                    start_time.strftime("%H:%M:%S") if start_time else None,
                    end_time.strftime("%H:%M:%S") if end_time else None,
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    expanded_instances.append({
                        "date": start_date.isoformat(),
                        "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
                        "end_time": end_time.strftime("%H:%M:%S") if end_time else None,
                        "all_day": all_day,
                    })

    # If ISO parsing produced instances and no upcoming dates override, return them
    if expanded_instances and not upcoming_dates:
        return expanded_instances

    # 2. Fallback / Additional: Parse from raw strings & upcoming dates list
    start_time, end_time = parse_time_range(raw_time_str)
    if not start_time:
        start_time, end_time = parse_time_range(raw_date_str)
    if not start_time and raw_recur_str:
        start_time, end_time = parse_time_range(raw_recur_str)

    weekday_pattern = parse_weekday_pattern(raw_recur_str)
    if not weekday_pattern and raw_date_str:
        weekday_pattern = parse_weekday_pattern(raw_date_str)
    if not weekday_pattern and overview_text:
        if re.search(r"\bevery\s+(friday|saturday|sunday|monday|tuesday|wednesday|thursday)\b", overview_text, re.IGNORECASE):
            weekday_pattern = parse_weekday_pattern(overview_text)

    date_ranges: List[Tuple[datetime.date, datetime.date, Optional[Set[int]]]] = []

    if upcoming_dates:
        for u_date in upcoming_dates:
            u_date_clean = strip_time_expressions(u_date)
            parsed_ranges = parse_date_range_or_single(u_date_clean, base_date)
            item_weekdays = parse_weekday_pattern(u_date) or weekday_pattern
            for d1, d2 in parsed_ranges:
                date_ranges.append((d1, d2, item_weekdays))
    elif not expanded_instances:
        raw_date_clean = strip_time_expressions(raw_date_str)
        parsed_ranges = parse_date_range_or_single(raw_date_clean, base_date)
        for d1, d2 in parsed_ranges:
            date_ranges.append((d1, d2, weekday_pattern))

    for d1, d2, pattern in date_ranges:
        day_count = (d2 - d1).days + 1
        if day_count > 366:
            day_count = 366

        for i in range(day_count):
            day = d1 + datetime.timedelta(days=i)
            if pattern is not None and day.weekday() not in pattern:
                continue

            key = (
                day.isoformat(),
                start_time.strftime("%H:%M:%S") if start_time else None,
                end_time.strftime("%H:%M:%S") if end_time else None,
            )
            if key not in seen_keys:
                seen_keys.add(key)
                expanded_instances.append({
                    "date": day.isoformat(),
                    "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
                    "end_time": end_time.strftime("%H:%M:%S") if end_time else None,
                    "all_day": start_time is None,
                })

    return expanded_instances
