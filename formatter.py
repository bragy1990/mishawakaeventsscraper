"""
iCalendar (.ics) formatting functions for the City of Mishawaka Events Scraper.
"""

import datetime
import hashlib
import logging
from typing import Any, Dict, List

try:
    from .config import TIMEZONE_ID
except ImportError:
    from config import TIMEZONE_ID

logger = logging.getLogger("MishawakaScraper")


def ical_escape(text: str) -> str:
    """Escape special characters in iCalendar property values (RFC 5545)."""
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", r"\;")
    text = text.replace(",", r"\,")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\n")
    return text


def fold_line(line: str, max_length: int = 75) -> str:
    """Fold long lines at 75 octets with a leading space continuation per RFC 5545."""
    if len(line.encode("utf-8")) <= max_length:
        return line

    result: List[str] = []
    current_line = ""
    current_bytes = 0

    for char in line:
        char_bytes = len(char.encode("utf-8"))
        limit = max_length if not result else max_length - 1
        if current_bytes + char_bytes > limit:
            result.append(current_line)
            current_line = " " + char
            current_bytes = 1 + char_bytes
        else:
            current_line += char
            current_bytes += char_bytes

    if current_line:
        result.append(current_line)

    return "\r\n".join(result)


def generate_uid(event_url: str, date_str: str, time_str: str) -> str:
    """Generate a deterministic, unique UID for each calendar instance."""
    unique_payload = f"{event_url}_{date_str}_{time_str or 'allday'}"
    h = hashlib.sha256(unique_payload.encode("utf-8")).hexdigest()[:24]
    return f"{h}@mishawaka.in.gov"


def build_ics_calendar(events: List[Dict[str, Any]]) -> str:
    """Generate a valid RFC 5545 iCalendar (.ics) string from extracted event listings."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//City of Mishawaka Events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:City of Mishawaka Events",
        f"X-WR-TIMEZONE:{TIMEZONE_ID}",
        # VTIMEZONE component for America/Indiana/Indianapolis
        "BEGIN:VTIMEZONE",
        f"TZID:{TIMEZONE_ID}",
        "BEGIN:STANDARD",
        "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "TZNAME:EST",
        "END:STANDARD",
        "BEGIN:DAYLIGHT",
        "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "TZNAME:EDT",
        "END:DAYLIGHT",
        "END:VTIMEZONE",
    ]

    for event in events:
        title = event.get("title") or "City of Mishawaka Event"
        url = event.get("url") or ""
        location = event.get("location") or ""
        description = event.get("description") or ""

        full_description = description
        if url:
            full_description = f"{description}\n\nMore Info: {url}" if description else f"More Info: {url}"

        instances = event.get("schedule_instances") or []
        for inst in instances:
            date_str = inst.get("date")  # YYYY-MM-DD
            if not date_str:
                continue

            try:
                dt_date = datetime.date.fromisoformat(date_str)
            except (ValueError, TypeError):
                logger.warning(f"Skipping invalid date '{date_str}' for event '{title}'")
                continue

            start_time_str = inst.get("start_time")  # HH:MM:SS
            end_time_str = inst.get("end_time")  # HH:MM:SS
            all_day = inst.get("all_day", False)

            uid = generate_uid(url, date_str, start_time_str or "")

            event_lines = [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"SUMMARY:{ical_escape(title)}",
            ]

            if location:
                event_lines.append(f"LOCATION:{ical_escape(location)}")
            if full_description:
                event_lines.append(f"DESCRIPTION:{ical_escape(full_description)}")
            if url:
                event_lines.append(f"URL:{url}")

            if all_day or not start_time_str:
                # Full day event: DTSTART;VALUE=DATE:YYYYMMDD, DTEND = +1 day (exclusive per RFC 5545)
                dtstart_val = dt_date.strftime("%Y%m%d")
                dtend_val = (dt_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
                event_lines.append(f"DTSTART;VALUE=DATE:{dtstart_val}")
                event_lines.append(f"DTEND;VALUE=DATE:{dtend_val}")
            else:
                # Timed event with explicit timezone notation
                try:
                    st = datetime.time.fromisoformat(start_time_str)
                    dtstart_dt = datetime.datetime.combine(dt_date, st)
                    dtstart_formatted = dtstart_dt.strftime("%Y%m%dT%H%M%S")
                    event_lines.append(f"DTSTART;TZID={TIMEZONE_ID}:{dtstart_formatted}")

                    if end_time_str:
                        try:
                            et = datetime.time.fromisoformat(end_time_str)
                            dtend_dt = datetime.datetime.combine(dt_date, et)
                            if dtend_dt <= dtstart_dt:
                                dtend_dt += datetime.timedelta(days=1)
                        except (ValueError, TypeError):
                            dtend_dt = dtstart_dt + datetime.timedelta(hours=1)
                    else:
                        dtend_dt = dtstart_dt + datetime.timedelta(hours=1)

                    dtend_formatted = dtend_dt.strftime("%Y%m%dT%H%M%S")
                    event_lines.append(f"DTEND;TZID={TIMEZONE_ID}:{dtend_formatted}")
                except (ValueError, TypeError):
                    dtstart_val = dt_date.strftime("%Y%m%d")
                    dtend_val = (dt_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
                    event_lines.append(f"DTSTART;VALUE=DATE:{dtstart_val}")
                    event_lines.append(f"DTEND;VALUE=DATE:{dtend_val}")

            event_lines.append("STATUS:CONFIRMED")
            event_lines.append("END:VEVENT")

            for line in event_lines:
                lines.append(fold_line(line))

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
