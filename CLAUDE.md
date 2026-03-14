# CLAUDE.md

This file provides guidance to Claude Code when working with SentinelStack.

## Project Overview

SentinelStack is a personal multi-agent geopolitical and physical threat intelligence tool for a GSOC analyst. It collects OSINT from 4 sources, scores articles with Gemini, and produces crisis-communications reports for leadership.

**Pipeline:** Collector → Analyst → Writer

## Commands

```bash
# Collect
python main.py collect --source all
python main.py collect --source osac
python main.py collect --source reliefweb
python main.py collect --source usgs
python main.py collect --source gdacs
python main.py health

# Analyze
python main.py analyze
python main.py analyze --dry-run

# Write reports
python main.py write --tier flash
python main.py write --tier priority
python main.py write --tier routine
python main.py write --tier all

# Review
python main.py show --tier all
python main.py show --tier flash --limit 5
```

Install:
```bash
pip install -r requirements.txt
```

## Architecture

Three sequential agents. Each has a SKILL.md in `skills/`.

### Collector (`collector/`)
- Fetches from OSAC, ReliefWeb, USGS, GDACS
- Stores `Article` records in `articles` table
- `INSERT OR IGNORE` — no dedup at collection time
- All source classes inherit `BaseSource` from `collector/base.py`

### Analyst (`analyst/`)
- Loads `articles WHERE analyzed=0`
- Deduplicates by `content_hash` within 24h window
- Gemini `is_noise()` → skip if noise
- Gemini `score_severity()` → int 1-10
- Tier: 8-10=FLASH, 5-7=PRIORITY, 1-4=ROUTINE (hard rules, not Gemini)
- Writes to `scored_events` table

### Writer (`writer/`)
- Loads `scored_events WHERE is_noise=0 AND reported=0`
- Groups by `(country, category)`
- One Gemini call per group → `{title, situation, impact, action}`
- Prints crisis-comms format to terminal (color-coded)
- Writes to `reports` table; marks events `reported=1`

## Key Files

| File | Purpose |
|---|---|
| `collector/base.py` | `Article` dataclass, `BaseSource` ABC, `generate_article_id()`, `generate_content_hash()` |
| `collector/store.py` | SQLite init (all 3 tables), `get_conn()`, `bulk_insert()` |
| `analyst/filter.py` | `is_noise()`, `score_severity()`, `run_analysis()`, `ScoredEvent` dataclass |
| `writer/reporter.py` | `run_writer()`, `show_reports()`, `Report` dataclass, rich terminal output |
| `main.py` | CLI entry point — click groups wiring all agents |
| `config/sources.json` | Source URLs, params, alert filters |
| `config/watchlist.json` | Countries, regions, keywords to monitor |
| `config/.env` | `GEMINI_API_KEY` — gitignored |
| `data/sentinel.db` | Single SQLite DB — articles, scored_events, reports |
| `skills/` | SKILL.md files for each agent |

## Code Conventions

- Type hints on all functions
- Dataclasses for all data structures
- `logging` module — `logger = logging.getLogger(__name__)`
- `click` + `rich` for CLI
- Every source subclasses `BaseSource` and implements `source_name`, `fetch()`, `health_check()`
- USGS GeoJSON coords: `[longitude, latitude, depth]` — `coords[0]`=lon, `coords[1]`=lat
- Gemini JSON responses: always wrap parse in try/except with sensible fallback
- Dates: always store as ISO8601 UTC string; parse with `dateutil.parser.parse()`

## Database

Single `data/sentinel.db` with 3 tables:
- `articles` — raw collected articles (`analyzed` flag)
- `scored_events` — Gemini-scored events (`reported` flag)
- `reports` — generated crisis-comms reports (`printed` flag)

## Gemini Models

- Analyst: `gemini-1.5-flash` (temp=0) — fast classification
- Writer: `gemini-1.5-pro` (temp=0.3) — higher quality writing
