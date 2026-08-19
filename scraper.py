"""
Main scraper implementation for the City of Mishawaka Events Scraper.
"""

import asyncio
import datetime
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

try:
    from .config import (
        BASE_URL,
        BROWSER_CONFIG,
        CALENDAR_URL,
        EVENTS_BASE_URL,
        EXCLUDED_PATHS,
        MAX_CONCURRENT_REQUESTS,
        MONTH_LOOKAHEAD,
        OUTPUT_ICS_PATH,
        OUTPUT_JSON_PATH,
        PAGE_LOAD_TIMEOUT_MS,
        WEBHOOK_URL,
    )
    from .formatter import build_ics_calendar
    from .parsers import clean_text
    from .utils import expand_event_schedules, format_location_address
except ImportError:
    from config import (
        BASE_URL,
        BROWSER_CONFIG,
        CALENDAR_URL,
        EVENTS_BASE_URL,
        EXCLUDED_PATHS,
        MAX_CONCURRENT_REQUESTS,
        MONTH_LOOKAHEAD,
        OUTPUT_ICS_PATH,
        OUTPUT_JSON_PATH,
        PAGE_LOAD_TIMEOUT_MS,
        WEBHOOK_URL,
    )
    from formatter import build_ics_calendar
    from parsers import clean_text
    from utils import expand_event_schedules, format_location_address

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MishawakaScraper")


def detect_event_diffs(old_events: List[Dict[str, Any]], new_events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Compare previous event dataset against newly scraped dataset to identify added and removed events."""
    old_by_url = {e.get("url"): e for e in old_events if e.get("url")}
    new_by_url = {e.get("url"): e for e in new_events if e.get("url")}

    added = [e for url, e in new_by_url.items() if url not in old_by_url]
    removed = [e for url, e in old_by_url.items() if url not in new_by_url]

    return {
        "added": added,
        "removed": removed,
    }


def dispatch_webhook(
    webhook_url: str,
    diff: Dict[str, List[Dict[str, Any]]],
    total_events: int,
    total_instances: int,
) -> bool:
    """Send an outbound notification payload to a Discord, Slack, or generic webhook endpoint."""
    if not webhook_url:
        return False

    added_events = diff.get("added", [])
    removed_events = diff.get("removed", [])

    # Format notification content
    summary_lines = [
        "📅 **City of Mishawaka Events Calendar Updated**",
        f"• Total Active Events: **{total_events}** ({total_instances} calendar entries)",
    ]

    if added_events:
        summary_lines.append(f"\n✨ **Newly Discovered Events ({len(added_events)}):**")
        for e in added_events[:5]:
            title = e.get("title", "Event")
            url = e.get("url", "")
            summary_lines.append(f"- [{title}]({url})" if url else f"- {title}")
        if len(added_events) > 5:
            summary_lines.append(f"_...and {len(added_events) - 5} more_")

    if removed_events:
        summary_lines.append(f"\n🗑️ **Removed Events ({len(removed_events)}):**")
        for e in removed_events[:3]:
            summary_lines.append(f"- {e.get('title', 'Event')}")

    message_text = "\n".join(summary_lines)

    payload = {
        "content": message_text,
        "text": message_text,
        "total_events": total_events,
        "total_instances": total_instances,
        "added_count": len(added_events),
        "removed_count": len(removed_events),
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MishawakaScraper/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            logger.info(f"Dispatched webhook notification (HTTP status {response.status}).")
            return True
    except Exception as e:
        logger.warning(f"Failed to dispatch webhook notification: {e}")
        return False


async def discover_event_urls_from_page(page: Page, url: str) -> Set[str]:
    """Navigate to a given calendar or list view page and extract unique event links."""
    discovered: Set[str] = set()
    try:
        logger.info(f"Navigating to discovery page: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        await page.wait_for_timeout(1500)

        links = await page.evaluate(
            """() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
        }"""
        )

        for href in links:
            parsed = urlparse(href)
            path = parsed.path.rstrip("/")
            if "/event/" in parsed.path:
                if (
                    path not in EXCLUDED_PATHS
                    and f"{path}/" not in EXCLUDED_PATHS
                    and not href.endswith("#")
                    and parsed.netloc.endswith("mishawaka.in.gov")
                ):
                    clean_url = urljoin(BASE_URL, parsed.path)
                    if not clean_url.endswith("/"):
                        clean_url += "/"
                    discovered.add(clean_url)
    except Exception as e:
        logger.warning(f"Failed discovering URLs on {url}: {e}")

    return discovered


async def discover_all_event_urls(context: BrowserContext) -> List[str]:
    """Discover event URLs across the main calendar, upcoming month views, and list pagination."""
    today = datetime.date.today()
    all_urls: Set[str] = set()
    page = await context.new_page()

    try:
        # 1. Main Calendar Page
        main_page_urls = await discover_event_urls_from_page(page, CALENDAR_URL)
        all_urls.update(main_page_urls)

        # 2. Upcoming Month Views
        for i in range(MONTH_LOOKAHEAD):
            m = ((today.month - 1 + i) % 12) + 1
            y = today.year + ((today.month - 1 + i) // 12)
            month_str = f"{y:04d}-{m:02d}"
            month_url = f"{EVENTS_BASE_URL}month/{month_str}/"
            month_urls = await discover_event_urls_from_page(page, month_url)
            all_urls.update(month_urls)

        # 3. List View Pagination (crawl up to 4 pages)
        for page_num in range(1, 5):
            list_url = f"{EVENTS_BASE_URL}list/page/{page_num}/" if page_num > 1 else f"{EVENTS_BASE_URL}list/"
            list_page_urls = await discover_event_urls_from_page(page, list_url)
            if not list_page_urls:
                break
            all_urls.update(list_page_urls)

    finally:
        await page.close()

    logger.info(f"Discovered {len(all_urls)} unique event detail links in total.")
    return sorted(list(all_urls))


async def extract_event_detail(context: BrowserContext, event_url: str, base_date: datetime.date) -> Optional[Dict[str, Any]]:
    """Visit an individual event detail page and extract structured metadata."""
    page: Optional[Page] = None
    try:
        page = await context.new_page()
        logger.info(f"Scraping detail page: {event_url}")
        await page.goto(event_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        await page.wait_for_timeout(1200)

        extracted = await page.evaluate(
            """() => {
            // 1. Check Schema.org JSON-LD for Event
            let jsonLdEvent = null;
            const scriptTags = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
            for (const script of scriptTags) {
                try {
                    const data = JSON.parse(script.innerText);
                    if (data['@type'] === 'Event') {
                        jsonLdEvent = data;
                        break;
                    }
                    if (Array.isArray(data['@graph'])) {
                        const ev = data['@graph'].find(item => item['@type'] === 'Event');
                        if (ev) {
                            jsonLdEvent = ev;
                            break;
                        }
                    }
                } catch (e) {}
            }

            // 2. DOM Title
            let domTitle = document.querySelector('h1.tribe-events-single-event-title, h1.elementor-heading-title, h1')?.innerText?.trim() || '';
            if (!domTitle || domTitle.toLowerCase() === 'navigation') {
                domTitle = document.title.replace(' - City of Mishawaka', '').trim();
            }

            // 3. Datetime from DOM
            const domDatetime = document.querySelector('.tec-events-elementor-event-widget__datetime, .tribe-events-schedule, [class*="event-datetime"]')?.innerText?.trim() || '';

            // 4. Venue & Address from DOM
            let domVenue = document.querySelector('.tribe-events-venue-details, .tribe-block__venue, [class*="venue"]')?.innerText?.trim() || '';
            let domAddress = document.querySelector('.tribe-events-address, .tribe-address, [class*="address"]')?.innerText?.trim() || '';

            // 5. Description from DOM
            let domDescription = '';
            const descEl = document.querySelector('.tribe-events-single-event-description, .tribe-block__event-description, .elementor-widget-theme-post-content');
            if (descEl) {
                domDescription = descEl.innerText.trim();
            }

            return {
                jsonLd: jsonLdEvent,
                domTitle,
                domDatetime,
                domVenue,
                domAddress,
                domDescription,
            };
        }"""
        )

        json_ld = extracted.get("jsonLd") or {}

        # Title extraction
        title = clean_text(json_ld.get("name") or extracted.get("domTitle") or "")
        if not title:
            slug = event_url.rstrip("/").split("/")[-1]
            title = slug.replace("-", " ").title()

        # Date & Time extraction
        iso_start = json_ld.get("startDate")
        iso_end = json_ld.get("endDate")
        dom_datetime = extracted.get("domDatetime") or ""

        # Location extraction
        venue_name = ""
        street_address = ""
        city_state_zip = ""

        if json_ld.get("location") and isinstance(json_ld["location"], dict):
            loc = json_ld["location"]
            venue_name = loc.get("name", "")
            addr = loc.get("address", {})
            if isinstance(addr, dict):
                street_address = addr.get("streetAddress", "")
                locality = addr.get("addressLocality", "")
                region = addr.get("addressRegion", "IN")
                postal = addr.get("postalCode", "")
                city_state_zip = f"{locality}, {region} {postal}".strip(", ")

        if not venue_name and extracted.get("domVenue"):
            venue_name = clean_text(extracted["domVenue"])
        if not street_address and extracted.get("domAddress"):
            street_address = clean_text(extracted["domAddress"])

        location = format_location_address(venue_name, street_address, city_state_zip)

        # Description extraction
        raw_desc = json_ld.get("description") or extracted.get("domDescription") or ""
        description = clean_text(raw_desc)
        if description.upper().startswith("HOME »") or description.upper().startswith("HOME >"):
            description = ""

        # Schedule instances
        schedule_instances = expand_event_schedules(
            iso_start_str=iso_start,
            iso_end_str=iso_end,
            raw_date_str=dom_datetime,
            raw_time_str=dom_datetime,
            raw_recur_str="",
            upcoming_dates=[],
            overview_text=description,
            base_date=base_date,
        )

        event_data = {
            "title": title,
            "url": event_url,
            "location": location,
            "description": description,
            "iso_start": iso_start,
            "iso_end": iso_end,
            "schedule_instances": schedule_instances,
        }

        return event_data

    except Exception as e:
        logger.error(f"Error scraping detail page {event_url}: {e}")
        return None
    finally:
        if page:
            await page.close()


async def main():
    """Main execution pipeline."""
    logger.info("Starting City of Mishawaka Events Scraper...")
    base_date = datetime.date.today()

    # Load existing events for diff detection if available
    old_events: List[Dict[str, Any]] = []
    if os.path.exists(OUTPUT_JSON_PATH):
        try:
            with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                old_events = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load existing {OUTPUT_JSON_PATH} for diffing: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=BROWSER_CONFIG["user_agent"],
                viewport=BROWSER_CONFIG["viewport"],
            )

            # Step 1: Discover all event detail URLs
            event_urls = await discover_all_event_urls(context)

            # Step 2: Extract details for each event concurrently
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

            async def worker(url: str):
                async with semaphore:
                    return await extract_event_detail(context, url, base_date)

            tasks = [worker(url) for url in event_urls]
            extracted_results = await asyncio.gather(*tasks)
            events = [e for e in extracted_results if e is not None]
        finally:
            await browser.close()

    logger.info(f"Successfully scraped {len(events)} events.")

    # Step 3: Compute diffs against previous run
    diff = detect_event_diffs(old_events, events)
    if diff["added"]:
        logger.info(f"Discovered {len(diff['added'])} new events.")
    if diff["removed"]:
        logger.info(f"{len(diff['removed'])} previously listed events have completed/been removed.")

    # Step 4: Save raw JSON output
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved raw extracted events to {OUTPUT_JSON_PATH}")

    # Step 5: Generate and save iCalendar .ics file
    ics_content = build_ics_calendar(events)
    with open(OUTPUT_ICS_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(ics_content)
    logger.info(f"Saved generated iCalendar to {OUTPUT_ICS_PATH}")

    total_instances = sum(len(e.get("schedule_instances", [])) for e in events)
    logger.info(f"Pipeline complete: {len(events)} events converted into {total_instances} calendar entries.")

    # Step 6: Dispatch outbound webhook if configured
    if WEBHOOK_URL:
        dispatch_webhook(WEBHOOK_URL, diff, len(events), total_instances)


if __name__ == "__main__":
    asyncio.run(main())
