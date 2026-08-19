"""
Date, time, ISO, and text parsing functions for the City of Mishawaka Events Scraper.
"""

import datetime
import html
import re
from typing import Dict, List, Optional, Set, Tuple

try:
    from .config import MONTH_NAME_TO_INT, WEEKDAY_NAME_TO_INT
except ImportError:
    from config import MONTH_NAME_TO_INT, WEEKDAY_NAME_TO_INT


def clean_text(text: Optional[str]) -> str:
    """Normalize whitespace, unescape HTML entities, and standardize dash/hyphen characters."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-–—]", " - ", text)
    text = re.sub(r"[\u00a0\xa0]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_iso_datetime(iso_str: Optional[str]) -> Tuple[Optional[datetime.date], Optional[datetime.time]]:
    """Parse an ISO 8601 string (e.g. '2026-08-18T10:00:00-04:00', '2026-08-18T10:00:00', '2026-08-18')."""
    if not iso_str:
        return None, None
    iso_str = iso_str.strip()
    try:
        # Date only: YYYY-MM-DD
        if len(iso_str) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", iso_str):
            d = datetime.date.fromisoformat(iso_str)
            return d, None

        # Full ISO datetime with optional timezone offset
        dt = datetime.datetime.fromisoformat(iso_str)
        return dt.date(), dt.time()
    except (ValueError, TypeError):
        # Fallback regex extraction for date and time in ISO format
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}(?::\d{2})?))?", iso_str)
        if m:
            try:
                d = datetime.date.fromisoformat(m.group(1))
                t = datetime.time.fromisoformat(m.group(2)) if m.group(2) else None
                return d, t
            except (ValueError, TypeError):
                pass
    return None, None


def strip_time_expressions(text: str) -> str:
    """Remove time expressions (e.g., '10:00 am - 11:00 am', '7:00 PM', 'Noon - 5:00 PM') from date strings."""
    text = clean_text(text)
    time_marker = r"(?:\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|noon|midnight)"
    any_time = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"

    # Remove time ranges where at least one side has an explicit time indicator
    text = re.sub(rf"{time_marker}\s*-\s*{any_time}", "", text, flags=re.IGNORECASE)
    text = re.sub(rf"{any_time}\s*-\s*{time_marker}", "", text, flags=re.IGNORECASE)
    # Remove standalone times
    text = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b(?:noon|midnight)\b|\b\d{1,2}:\d{2}\b", "", text, flags=re.IGNORECASE)
    return clean_text(text)


def parse_time_string(time_str: str) -> Optional[datetime.time]:
    """Parse time representations such as '7:00 PM', '10:00 am', '12:30 AM', 'Noon', 'Midnight', '5 PM'."""
    time_str = clean_text(time_str).lower()
    if time_str == "noon":
        return datetime.time(12, 0)
    if time_str == "midnight":
        return datetime.time(0, 0)

    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", time_str)
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2)) if m.group(2) else 0
    meridiem = m.group(3)

    if meridiem == "pm" and hours < 12:
        hours += 12
    elif meridiem == "am" and hours == 12:
        hours = 0
    elif not meridiem and hours > 23:
        return None

    try:
        return datetime.time(hours, minutes)
    except ValueError:
        return None


def parse_time_range(text: str) -> Tuple[Optional[datetime.time], Optional[datetime.time]]:
    """Parse time expressions into start and end times (e.g. '10:00 am - 11:00 am', '7:00 PM - 9:00 PM', 'Noon - 5:00 PM')."""
    text_clean = clean_text(text)

    # 1. Range match: require at least one side to have an explicit time indicator
    time_marker = r"(?:\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)|noon|midnight)"
    any_time = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"

    range_match = re.search(rf"({time_marker})\s*-\s*({any_time})", text_clean, re.IGNORECASE)
    if not range_match:
        range_match = re.search(rf"({any_time})\s*-\s*({time_marker})", text_clean, re.IGNORECASE)

    if range_match:
        t1_str, t2_str = range_match.group(1).strip(), range_match.group(2).strip()
        t2 = parse_time_string(t2_str)

        if (
            not re.search(r"am|pm", t1_str, re.IGNORECASE)
            and re.search(r"am|pm", t2_str, re.IGNORECASE)
            and t1_str.lower() not in ("noon", "midnight")
        ):
            meridiem = re.search(r"am|pm", t2_str, re.IGNORECASE).group(0).lower()
            t1_hour_match = re.match(r"^(\d{1,2})", t1_str)
            t1_hour = int(t1_hour_match.group(1)) if t1_hour_match else 0

            # If t2 is PM and t1_hour > t2's 12-hour value (and t1_hour != 12), t1 is AM
            # Example: "10:00 - 2:00 PM" -> 10:00 AM to 2:00 PM
            if meridiem == "pm" and t2 and t1_hour > (t2.hour % 12) and t1_hour != 12:
                t1 = parse_time_string(f"{t1_str} am")
            else:
                t1 = parse_time_string(f"{t1_str} {meridiem}")
        else:
            t1 = parse_time_string(t1_str)

        return t1, t2

    # 2. Standalone start time match: "7:00 PM", "10:00 am", "Noon"
    single_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon|midnight)", text_clean, re.IGNORECASE)
    if single_match:
        t = parse_time_string(single_match.group(1))
        return t, None

    return None, None


def parse_weekday_pattern(text: str) -> Optional[Set[int]]:
    """Detect recurring weekday patterns (e.g. 'Wednesday - Sunday', 'Fridays', 'Every Saturday', 'Mon-Fri')."""
    text = clean_text(text).lower()
    day_regex = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"

    # Check for weekday range: e.g. "Wednesday - Sunday"
    range_match = re.search(rf"\b{day_regex}\s*-\s*{day_regex}\b", text)
    if range_match:
        start_day = WEEKDAY_NAME_TO_INT[range_match.group(1)]
        end_day = WEEKDAY_NAME_TO_INT[range_match.group(2)]
        if start_day <= end_day:
            return set(range(start_day, end_day + 1))
        else:
            return set(list(range(start_day, 7)) + list(range(0, end_day + 1)))

    # Check for individual or plural day names: "Fridays", "Friday", "Saturdays and Sundays"
    days = set()
    for name, day_num in WEEKDAY_NAME_TO_INT.items():
        if re.search(rf"\b{name}s?\b", text):
            days.add(day_num)

    if days:
        return days
    return None


def resolve_year(month: int, day: int, base_date: datetime.date) -> int:
    """Correctly resolve the year for upcoming events relative to base_date."""
    year = base_date.year
    safe_day = min(day, 28)
    try:
        candidate_date = datetime.date(year, month, safe_day)
        # If candidate date is more than 60 days in the past, roll over to next year
        if candidate_date < (base_date - datetime.timedelta(days=60)):
            year += 1
    except ValueError:
        if month < base_date.month:
            year += 1
    return year


def parse_date_segment(seg: str, base_date: datetime.date) -> Optional[datetime.date]:
    """Parse a single date component like 'August 18', 'Aug 18th', 'Wednesday, August 18', 'August 18, 2026'."""
    seg = clean_text(seg)
    year_match = re.search(r"\b(202\d|203\d)\b", seg)
    explicit_year = int(year_match.group(1)) if year_match else None

    # Match Month + Day (e.g. "August 18", "August 18th", "Aug 1st")
    m = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b\.?\s*(\d{1,2})(?:st|nd|rd|th)?\b",
        seg,
        re.IGNORECASE,
    )
    if not m:
        # Match Day + Month (e.g. "18 August", "18th August", "1st Aug")
        m = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b",
            seg,
            re.IGNORECASE,
        )
        if m:
            day = int(m.group(1))
            month_str = m.group(2).lower()
        else:
            return None
    else:
        month_str = m.group(1).lower()
        day = int(m.group(2))

    month = MONTH_NAME_TO_INT.get(month_str)
    if not month:
        return None

    year = explicit_year if explicit_year else resolve_year(month, day, base_date)
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def parse_date_range_or_single(date_text: str, base_date: datetime.date) -> List[Tuple[datetime.date, datetime.date]]:
    """Parse complex date strings: 'Aug 17 to Aug 23', 'Aug 17 - 23', 'Friday, August 21 to Friday, December 11', 'Aug 19'."""
    normalized = re.sub(r"\b(to|through)\b", " - ", date_text, flags=re.IGNORECASE)
    normalized = clean_text(normalized)

    # 1. Format: "Month Day1 - Day2" (e.g. "Aug 17 - 23", "August 17th - 23rd, 2026")
    m_same_month = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b\.?\s*(\d{1,2})(?:st|nd|rd|th)?\s*-\s*(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(202\d|203\d))?",
        normalized,
        re.IGNORECASE,
    )
    if m_same_month:
        month_str = m_same_month.group(1).lower()
        day1 = int(m_same_month.group(2))
        day2 = int(m_same_month.group(3))
        explicit_year = int(m_same_month.group(4)) if m_same_month.group(4) else None
        month = MONTH_NAME_TO_INT[month_str]
        year = explicit_year if explicit_year else resolve_year(month, day1, base_date)
        try:
            d1 = datetime.date(year, month, day1)
            d2 = datetime.date(year, month, day2)
            return [(d1, d2)]
        except ValueError:
            pass

    # 2. Format: "DateSeg1 - DateSeg2" (e.g. "Aug 21 - Dec 11", "August 21 to December 18")
    if " - " in normalized:
        parts = normalized.split(" - ")
        if len(parts) >= 2:
            d1 = parse_date_segment(parts[0], base_date)
            d2 = parse_date_segment(parts[-1], base_date)
            if d1 and d2:
                # Year Rollover: If d2 precedes d1, roll d2 to next year
                if d2 < d1 and d2.year == d1.year:
                    try:
                        d2 = datetime.date(d1.year + 1, d2.month, d2.day)
                    except ValueError:
                        d2 = datetime.date(d1.year + 1, d2.month, min(d2.day, 28))
                return [(d1, d2)]
            elif d1 and not d2:
                return [(d1, d1)]

    # 3. Single Date
    d = parse_date_segment(normalized, base_date)
    if d:
        return [(d, d)]

    return []
