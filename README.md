# Kirtan Search

A Telegram bot for searching and reading Swaminarayan kirtans from anirdesh.com. A local-only scraper builds `data/kirtans.db`; the deployed bot never imports or requires `scraper/`.

## Architecture

- **Python 3.12**, python-telegram-bot 21 with JobQueue, SQLite FTS5.
- `data/kirtans.db` is built locally, committed to Git, and opened with SQLite URI `mode=ro` plus `PRAGMA query_only=ON`.
- `state/users.db` contains only runtime user preferences. It and `heartbeat.txt` live on the Docker state volume.
- Long polling requires no domain, webhook, exposed port, or inbound firewall rule.
- `scraper/`, its raw cache, and its fixtures are ignored by Git and excluded from Docker builds.

The source site identifies kirtans by `(part, number)`. Buttons and `/k` therefore accept forms such as `2-285`. A bare number opens the only match or presents a numbered disambiguation list if both parts contain it.

## Commands

- `/start` — welcome message and main menu
- `/search <text>` — Gujarati, Hindi, transliterated title/lyric search
- `/k <number>` — open by number or `part-number`
- `/lang` — save the user's default language
- `/random` — open a random kirtan
- `/about` — kirtan count and scrape timestamp from `meta`
- `/help` — command help

Plain non-command text is a search; plain numbers act like `/k`. Search and browse results have ten buttons per page and numeric kirtan ordering. Inline mode returns up to 20 results with HTML-formatted content.

Enable inline mode with **BotFather → Bot Settings → Inline Mode**. Inline replies are limited by Telegram to one message, so an exceptionally long kirtan uses its first complete blockquote-safe part and retains the source link; the bot's normal kirtan view sends all parts.

## Local bot setup

First generate `data/kirtans.db` using the scraper instructions below. Then:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For local use, edit `.env` to use absolute local paths and your real token:

```dotenv
TELEGRAM_BOT_TOKEN=123456:your-token
ADMIN_CHAT_ID=123456789
KIRTANS_DB=/absolute/path/to/project/data/kirtans.db
STATE_DIR=/absolute/path/to/project/state
LOG_LEVEL=INFO
```

Start long polling:

```bash
python -m bot
```

Startup fails with a non-zero exit and a clear log if the token is missing, the content DB is absent/unreadable, required tables are missing, or `schema_version` differs from `common.schema.SCHEMA_VERSION`.

## Local scraper

The scraper is local-only and uses separate dependencies:

```bash
source .venv/bin/activate
pip install -r scraper/requirements.txt
python -m scraper
```

Other modes:

```bash
python -m scraper --refresh  # refresh list/menu responses only
python -m scraper --offline  # cache-only; no network access
```

Requests respect live `robots.txt`, use a descriptive User-Agent, wait one second between requests, and retry transport errors/429/5xx with exponential backoff. Every successful response is cached before parsing. Network failure stops the attempt rather than skipping remaining pages; rerunning reuses the cache.

A database is built **only with zero failed kirtans and zero unresolved warnings**. It is written to a temporary sibling file, checked with `VACUUM`, `ANALYZE`, `PRAGMA integrity_check`, and `journal_mode=DELETE`, then atomically swapped into `data/kirtans.db`. The final summary includes total/language/media counts, failures, warnings, and file size. Investigate sizes over 50 MB; GitHub rejects files over 100 MB. Commit the resulting database explicitly.

## Tests

Install the committed bot/test dependencies (the local scraper is not needed):

```bash
pip install -r requirements-dev.txt
pytest -q tests
```

To include the local parser suite as well:

```bash
pip install -r scraper/requirements.txt
pytest -q tests scraper/tests
```

Tests cover loose normalization, title-above-lyric ranking, integer ordering, read-only/startup validation, numeric disambiguation, language preferences, callback sizes, heartbeat health, balanced Telegram HTML, and splitting only at whole blockquote pads under 4,096 characters. `test_real_database.py` automatically skips until `data/kirtans.db` exists, then runs transliteration/Gujarati/Hindi queries and integrity checks against the real scrape.

## Docker and Dokploy

The Docker image copies only `common/`, `bot/`, and the committed content DB. It runs as UID `10001`, installs only `requirements.txt`, logs to stdout, and uses `bot.healthcheck` to reject a heartbeat older than 180 seconds.

Local container run:

```bash
docker build -t kirtan-search .
docker compose up -d
```

For a **Dokploy Dockerfile deployment**:

1. Commit `bot/`, `common/`, `data/kirtans.db`, `requirements.txt`, `Dockerfile`, and `.dockerignore` to the GitHub repository. Do not commit `.env`, `scraper/`, or `state/`.
2. Create a Dokploy application from that repository and select the root `Dockerfile`.
3. Set environment variables `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `KIRTANS_DB=/app/data/kirtans.db`, `STATE_DIR=/app/state`, and `LOG_LEVEL=INFO` in Dokploy's environment settings.
4. Mount a persistent named volume at **`/app/state`**. Do not mount anything over `/app/data`; deployments replace the read-only content DB with the Git version.
5. Deploy with restart policy `unless-stopped`. No port mapping, domain, TLS certificate, or webhook is required. Dokploy collects the container's stdout logs and Docker health status.

A `docker-compose.yml` with a named `kirtan-state` volume is also included for Compose-based deployments.

## Reliability notes

- The kirtan view uses one lyric blockquote per message and one collapsed translation blockquote. Pad numbers remain inside the lyric quote; source pad labels and dagger markers are cleaned, and alternative readings appear as compact notes. Bot buttons and metadata use plain text without emoji.
- Telegram HTML is escaped with `html.escape()` for every scraped string. Message splitting never cuts inside a `<blockquote>`. Three real source pads exceed Telegram's limit even as complete pads, so the formatter preserves their content by splitting at original newlines into complete, balanced continuation blockquotes; a single original line over the limit is rejected rather than corrupted.
- Language changes and previous/next navigation edit existing messages; multi-part views are edited part by part and controls stay on the last part.
- `message is not modified` is ignored. Other unexpected exceptions log a full traceback and alert `ADMIN_CHAT_ID` at most once per minute.
- Search sessions and active view message IDs are in-memory only; old pagination buttons gracefully ask for a new search after a restart.
- Runtime state uses a separate writable SQLite DB. The content DB is never opened writable by the bot.

