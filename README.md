# City of Mishawaka Events Scraper & Live Calendar Sync

An asynchronous scraper and automated iCalendar (`.ics`) generator for the [City of Mishawaka Calendar](https://mishawaka.in.gov/things-to-do/city-calendar/).

---

## 🌟 Features

- **Asynchronous Scraping**: Powered by Playwright with concurrency-controlled detail extraction across calendar month views, list pagination, and primary pages.
- **Smart Date & Time Extraction**: Parses high-fidelity Schema.org (`Event`) JSON-LD timestamps with timezone offsets and robust DOM fallback parsing.
- **RFC 5545 iCalendar Compliant**: Generates valid `.ics` calendars with strict 75-octet line folding, deterministic SHA-256 UIDs, character escaping, and `America/Indiana/Indianapolis` timezone definitions.
- **Automated GitHub Actions Sync**: Runs twice daily on a schedule or on demand via Inbound Webhooks.
- **Live Calendar Subscription**: Subscribe once via `webcal://` in Apple Calendar, Google Calendar, or Microsoft Outlook for automatic background updates.
- **Outbound Webhook Notifications**: Dispatches rich summary updates to Discord, Slack, or custom webhooks whenever new events are added or updated.

---

## 📁 Architecture

```text
MishawakaEventsScraper/
├── .github/
│   └── workflows/
│       └── update_calendar.yml   # GitHub Actions scheduled workflow & inbound webhook
├── tests/
│   └── test_scraper.py           # Unit tests for parsers, utils, and formatting
├── config.py                     # URLs, selectors, timezone, and webhook settings
├── parsers.py                    # Date, ISO timestamp, and time parsing functions
├── formatter.py                  # RFC 5545 iCalendar generation & line folding
├── utils.py                      # Address formatting and schedule expansion
├── scraper.py                    # Main Playwright scraping pipeline & diff detector
├── requirements.txt              # Project dependencies (Playwright, BeautifulSoup4)
├── actual_events.json            # Extracted raw event metadata
├── mishawaka_calendar.ics        # Generated iCalendar (.ics) file
└── README.md                     # Documentation & setup guide
```

---

## 🚀 Quick Start (Local Usage)

### 1. Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the Scraper

```bash
python scraper.py
```

This will:
1. Discover active event detail pages on Mishawaka's calendar (across current and upcoming months).
2. Extract structured metadata (title, dates, times, venue, description, etc.).
3. Save `actual_events.json` and `mishawaka_calendar.ics`.
4. (Optional) Dispatch a notification if `WEBHOOK_URL` is configured.

---

## ⚙️ Automated GitHub Actions & Live Calendar Setup

You can host this scraper on GitHub for **$0 / zero maintenance** and subscribe directly to the generated calendar feed.

### Step 1: Push Project to GitHub

```bash
git init
git add .
git commit -m "Initial commit: Mishawaka Events Scraper"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
git push -u origin main
```

### Step 2: Enable Workflow Permissions

In your GitHub repository:
1. Go to **Settings > Actions > General**.
2. Under **Workflow permissions**, select **Read and write permissions** (allows the workflow to commit updated calendar files).
3. Click **Save**.

---

## 📱 Subscribing in Calendar Clients (`webcal://`)

Once pushed to GitHub, your calendar file is permanently accessible at:
```text
https://raw.githubusercontent.com/bragy1990/mishawakaeventsscraper/main/mishawaka_calendar.ics
```

### Apple Calendar (iOS / macOS)
1. In Calendar on Mac, select **File > New Calendar Subscription...** (On iPhone/iPad: *Settings > Calendar > Accounts > Add Subscribed Calendar*).
2. Enter:
   ```text
   webcal://raw.githubusercontent.com/bragy1990/mishawakaeventsscraper/main/mishawaka_calendar.ics
   ```
3. Set Auto-Refresh to **Every hour** or **Every day**.

### Google Calendar
1. Open Google Calendar on the web.
2. In the left sidebar, next to **Other calendars**, click **+ > From URL**.
3. Paste the URL:
   ```text
   https://raw.githubusercontent.com/bragy1990/mishawakaeventsscraper/main/mishawaka_calendar.ics
   ```
4. Click **Add calendar**. Google Calendar will automatically poll and refresh the feed in the background.

### Microsoft Outlook
1. In Outlook, select **Add Calendar > Subscribe from web**.
2. Paste the URL and click **Import**.

---

## 🔗 Inbound Webhook: Trigger on Demand

You can trigger the scraper remotely (from a home server, Zapier, or website change monitor) by sending an HTTP POST request to GitHub's `repository_dispatch` endpoint:

```bash
curl -X POST https://api.github.com/repos/<YOUR_USERNAME>/<YOUR_REPO>/dispatches \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <YOUR_GITHUB_PAT>" \
  -d '{"event_type": "update-calendar"}'
```

> **Note**: `<YOUR_GITHUB_PAT>` is a GitHub Personal Access Token with `repo` or `contents:write` scope.

---

## 🔔 Outbound Webhooks (Discord / Slack Notifications)

To receive a notification whenever new events are added:
1. In your GitHub repository, go to **Settings > Secrets and variables > Actions**.
2. Add a new secret named `WEBHOOK_URL` containing your Discord or Slack webhook URL.
3. On every run with detected changes, a summary of added and removed events will be posted automatically.

---

## 🧪 Running Unit Tests

Run the built-in test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## 📄 License

MIT
