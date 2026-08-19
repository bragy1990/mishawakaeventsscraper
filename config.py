"""
Configuration settings for the City of Mishawaka Events Scraper.
"""

import os
from typing import Dict, Set

# Base URLs
BASE_URL = "https://mishawaka.in.gov"
CALENDAR_URL = "https://mishawaka.in.gov/things-to-do/city-calendar/"
EVENTS_BASE_URL = "https://mishawaka.in.gov/events/"

# Output file paths
OUTPUT_JSON_PATH = "actual_events.json"
OUTPUT_ICS_PATH = "mishawaka_calendar.ics"

# Timezone configuration
TIMEZONE_ID = "America/Indiana/Indianapolis"

# Webhook configuration (Optional: Discord, Slack, or generic HTTP POST)
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL") or ""

# Excluded URL paths or keywords that are not actual events
EXCLUDED_PATHS: Set[str] = {
    "/things-to-do/city-calendar/",
    "/things-to-do/city-calendar",
    "/events/",
    "/events",
    "/events/month/",
    "/events/month",
    "/events/list/",
    "/events/list",
}

# Browser configuration for scraping
BROWSER_CONFIG = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "viewport": {"width": 1440, "height": 900},
}

# Concurrency & Crawl settings
MAX_CONCURRENT_REQUESTS = 4
MONTH_LOOKAHEAD = 6
PAGE_LOAD_TIMEOUT_MS = 30000

# Date parsing configuration
MONTH_NAME_TO_INT: Dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

WEEKDAY_NAME_TO_INT: Dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
