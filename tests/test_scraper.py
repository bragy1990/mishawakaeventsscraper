"""
Unit tests for the City of Mishawaka Events Scraper modules.
"""

import datetime
import unittest

from config import MONTH_NAME_TO_INT, TIMEZONE_ID, WEEKDAY_NAME_TO_INT
from formatter import build_ics_calendar, fold_line, generate_uid, ical_escape
from parsers import (
    clean_text,
    parse_date_range_or_single,
    parse_date_segment,
    parse_iso_datetime,
    parse_time_range,
    parse_time_string,
    parse_weekday_pattern,
    resolve_year,
    strip_time_expressions,
)
from scraper import detect_event_diffs, dispatch_webhook
from utils import expand_event_schedules, format_location_address


class TestParsers(unittest.TestCase):
    def setUp(self):
        self.base_date = datetime.date(2026, 8, 18)

    def test_clean_text(self):
        self.assertEqual(clean_text("Event &#8211; Summer Series &amp; More"), "Event - Summer Series & More")
        self.assertEqual(clean_text("Hello\u00a0World   123"), "Hello World 123")
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text(None), "")

    def test_parse_iso_datetime(self):
        # Full ISO with timezone offset
        d, t = parse_iso_datetime("2026-08-18T10:00:00-04:00")
        self.assertEqual(d, datetime.date(2026, 8, 18))
        self.assertEqual(t, datetime.time(10, 0))

        # ISO date only
        d, t = parse_iso_datetime("2026-08-18")
        self.assertEqual(d, datetime.date(2026, 8, 18))
        self.assertIsNone(t)

        # Invalid string
        d, t = parse_iso_datetime("not-a-date")
        self.assertIsNone(d)
        self.assertIsNone(t)

    def test_parse_time_string(self):
        self.assertEqual(parse_time_string("Noon"), datetime.time(12, 0))
        self.assertEqual(parse_time_string("midnight"), datetime.time(0, 0))
        self.assertEqual(parse_time_string("10:00 am"), datetime.time(10, 0))
        self.assertEqual(parse_time_string("7:05 pm"), datetime.time(19, 5))
        self.assertEqual(parse_time_string("12:30 AM"), datetime.time(0, 30))
        self.assertEqual(parse_time_string("12:00 PM"), datetime.time(12, 0))
        self.assertEqual(parse_time_string("5 PM"), datetime.time(17, 0))
        self.assertIsNone(parse_time_string("invalid"))

    def test_parse_time_range(self):
        # Explicit AM and PM
        t1, t2 = parse_time_range("10:00 am - 11:00 am")
        self.assertEqual(t1, datetime.time(10, 0))
        self.assertEqual(t2, datetime.time(11, 0))

        # Inferred AM when start hour > end hour
        t1, t2 = parse_time_range("10:00 - 2:00 PM")
        self.assertEqual(t1, datetime.time(10, 0))
        self.assertEqual(t2, datetime.time(14, 0))

        # Standalone single time
        t1, t2 = parse_time_range("7:30 PM")
        self.assertEqual(t1, datetime.time(19, 30))
        self.assertIsNone(t2)

    def test_parse_weekday_pattern(self):
        self.assertEqual(parse_weekday_pattern("Wednesday - Sunday"), {2, 3, 4, 5, 6})
        self.assertEqual(parse_weekday_pattern("Mon-Fri"), {0, 1, 2, 3, 4})
        self.assertEqual(parse_weekday_pattern("Fridays"), {4})
        self.assertEqual(parse_weekday_pattern("Thursdays"), {3})
        self.assertIsNone(parse_weekday_pattern("Regular daily event"))

    def test_parse_date_segment(self):
        self.assertEqual(parse_date_segment("August 18", self.base_date), datetime.date(2026, 8, 18))
        self.assertEqual(parse_date_segment("Aug 18th", self.base_date), datetime.date(2026, 8, 18))
        self.assertEqual(parse_date_segment("September 2nd, 2026", self.base_date), datetime.date(2026, 9, 2))
        self.assertEqual(parse_date_segment("18th August 2026", self.base_date), datetime.date(2026, 8, 18))

    def test_resolve_year_and_rollover(self):
        self.assertEqual(resolve_year(8, 20, self.base_date), 2026)
        self.assertEqual(resolve_year(12, 15, self.base_date), 2026)
        self.assertEqual(resolve_year(1, 15, self.base_date), 2027)

    def test_parse_date_range_or_single(self):
        res = parse_date_range_or_single("Aug 17 - 23", self.base_date)
        self.assertEqual(res, [(datetime.date(2026, 8, 17), datetime.date(2026, 8, 23))])

        res = parse_date_range_or_single("August 21 to December 11", self.base_date)
        self.assertEqual(res, [(datetime.date(2026, 8, 21), datetime.date(2026, 12, 11))])


class TestUtils(unittest.TestCase):
    def setUp(self):
        self.base_date = datetime.date(2026, 8, 18)

    def test_format_location_address(self):
        loc = format_location_address(
            "City of Mishawaka, Board of Works Room",
            "100 Lincolnway West",
            "Mishawaka, IN 46544",
        )
        self.assertEqual(loc, "City of Mishawaka, Board of Works Room | 100 Lincolnway West | Mishawaka, IN 46544")

        loc_partial = format_location_address("Ironworks Plaza", "", "Mishawaka, IN")
        self.assertEqual(loc_partial, "Ironworks Plaza | Mishawaka, IN")

    def test_expand_event_schedules_from_iso(self):
        instances = expand_event_schedules(
            iso_start_str="2026-08-18T10:00:00-04:00",
            iso_end_str="2026-08-18T11:00:00-04:00",
            base_date=self.base_date,
        )
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["date"], "2026-08-18")
        self.assertEqual(instances[0]["start_time"], "10:00:00")
        self.assertEqual(instances[0]["end_time"], "11:00:00")
        self.assertFalse(instances[0]["all_day"])

    def test_expand_event_schedules_all_day(self):
        instances = expand_event_schedules(
            iso_start_str="2026-08-25",
            iso_end_str=None,
            base_date=self.base_date,
        )
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["date"], "2026-08-25")
        self.assertIsNone(instances[0]["start_time"])
        self.assertTrue(instances[0]["all_day"])


class TestFormatter(unittest.TestCase):
    def test_ical_escape(self):
        raw = "Meeting in Room A, with notes; & \\ backslash\r\nNext line"
        escaped = ical_escape(raw)
        self.assertIn(r"\,", escaped)
        self.assertIn(r"\;", escaped)
        self.assertIn(r"\\", escaped)
        self.assertIn(r"\nNext line", escaped)

    def test_fold_line(self):
        short_line = "SUMMARY:Board of Public Works Meeting."
        self.assertEqual(fold_line(short_line), short_line)

        long_line = "DESCRIPTION:" + "Mishawaka " * 20
        folded = fold_line(long_line)
        lines = folded.split("\r\n")
        self.assertTrue(len(lines) > 1)
        for i, l in enumerate(lines):
            self.assertTrue(len(l.encode("utf-8")) <= 75)
            if i > 0:
                self.assertTrue(l.startswith(" "))

    def test_generate_uid(self):
        uid1 = generate_uid("https://mishawaka.in.gov/event/meeting-1/", "2026-08-18", "10:00:00")
        uid2 = generate_uid("https://mishawaka.in.gov/event/meeting-1/", "2026-08-18", "10:00:00")
        uid3 = generate_uid("https://mishawaka.in.gov/event/meeting-2/", "2026-08-18", "10:00:00")

        self.assertEqual(uid1, uid2)
        self.assertNotEqual(uid1, uid3)
        self.assertTrue(uid1.endswith("@mishawaka.in.gov"))

    def test_build_ics_calendar(self):
        events = [
            {
                "title": "Rock The Block Party",
                "url": "https://mishawaka.in.gov/event/rock-the-block-party/",
                "location": "Ironworks Plaza | 235 Ironworks Ave | Mishawaka, IN 46544",
                "description": "Annual block party celebration.",
                "schedule_instances": [
                    {
                        "date": "2026-08-07",
                        "start_time": "17:00:00",
                        "end_time": "21:00:00",
                        "all_day": False,
                    }
                ],
            }
        ]

        ics = build_ics_calendar(events)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("VERSION:2.0", ics)
        self.assertIn("BEGIN:VTIMEZONE", ics)
        self.assertIn(f"TZID:{TIMEZONE_ID}", ics)
        self.assertIn("SUMMARY:Rock The Block Party", ics)
        self.assertIn(f"DTSTART;TZID={TIMEZONE_ID}:20260807T170000", ics)
        self.assertIn(f"DTEND;TZID={TIMEZONE_ID}:20260807T210000", ics)
        self.assertIn("END:VCALENDAR", ics)


class TestScraperDiffAndWebhook(unittest.TestCase):
    def test_detect_event_diffs(self):
        old_events = [
            {"title": "Old Meeting", "url": "https://mishawaka.in.gov/event/old-1/"},
            {"title": "Recurring Event", "url": "https://mishawaka.in.gov/event/recurring/"},
        ]
        new_events = [
            {"title": "Recurring Event", "url": "https://mishawaka.in.gov/event/recurring/"},
            {"title": "New Concert", "url": "https://mishawaka.in.gov/event/concert-1/"},
        ]

        diff = detect_event_diffs(old_events, new_events)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["title"], "New Concert")
        self.assertEqual(len(diff["removed"]), 1)
        self.assertEqual(diff["removed"][0]["title"], "Old Meeting")

    def test_dispatch_webhook_empty_url(self):
        res = dispatch_webhook("", {"added": [], "removed": []}, 10, 20)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
