# CLAUDE.md

This file provides guidance to Claude Code when working with SentinelStack.

## Project Overview

SentinelStack is a multi-agent geopolitical and physical threat intelligence tool for GSOC analysts at a tech company. It collects OSINT from 11 sources, scores articles with Groq (LLaMA 3.3) for relevance to tech industry operations, and produces crisis-communications reports for security leadership. Includes a web dashboard (Next.js) and on-demand intel chatbot. Reports auto-delete after 6 hours.

**Pipeline:** Collector → Analyst → Writer (auto-runs every 15 minutes)

## Commands

```bash
# Collect
python main.py collect --source all
python main.py collect --source un_news
python main.py collect --source bbc
python main.py collect --source aljazeera
python main.py collect --source reuters
python main.py collect --source cnn
python main.py collect --source fox
python main.py collect --source abc
python main.py collect --source skynews
python main.py collect --source usgs
python main.py collect --source gdacs
python main.py collect --source nws
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

# API server
uvicorn api.main:app --port 8000

# Frontend
cd web && npm run dev
```

Install:
```bash
pip install -r requirements.txt
```

## Architecture

Three sequential agents. Each has a SKILL.md in `skills/`.

### Collector (`collector/`)
- Fetches from UN News, BBC, Al Jazeera, Reuters, CNN, Fox, ABC, Sky News, USGS, GDACS, NWS
- Stores `Article` records in `articles` table (PostgreSQL on Railway)
- `ON CONFLICT DO NOTHING` — no dedup at collection time
- All source classes inherit `BaseSource` from `collector/base.py`
- RSS sources use `GenericRSSSource` from `collector/rss.py`

### Analyst (`analyst/`)
- Loads `articles WHERE analyzed=0`
- Deduplicates by `content_hash` within 24h window
- Groq `is_noise()` → skip if noise
- Groq `score_severity()` → int 1-10
- Tier: 8-10=FLASH, 5-7=PRIORITY, 1-4=ROUTINE (hard rules, not LLM)
- On LLM failure: skips article (does NOT mark analyzed), retries next run
- Writes to `scored_events` table

### Writer (`writer/`)
- Loads `scored_events WHERE is_noise=0 AND reported=0`
- Groups by `(country, category)`
- One Groq call per group → `{title, situation, impact, action}`
- Prints crisis-comms format to terminal (color-coded)
- Writes to `reports` table; marks events `reported=1`

### API (`api/`)
- FastAPI backend serving data to Next.js dashboard
- Pipeline trigger endpoints protected by `X-API-Key` header
- On-demand intel chatbot at `POST /api/chat` (DuckDuckGo search → Groq report)
- Auto-pipeline scheduler: collect → analyze → write every 15 min

### Web Dashboard (`web/`)
- Next.js 14 App Router
- Live feed, event chart, report workspace, chatbot
- Pipeline buttons with polling status
- Source health sidebar

## Key Files

| File | Purpose |
|---|---|
| `collector/base.py` | `Article` dataclass, `BaseSource` ABC, `build_source()` factory |
| `collector/rss.py` | `GenericRSSSource` — handles all RSS/Atom feeds |
| `collector/store.py` | PostgreSQL init (all tables), `get_conn()`, `bulk_insert()`, pipeline state |
| `analyst/llm.py` | `call_llm()` wrapper for Groq, `LLMError` exception |
| `analyst/filter.py` | `is_noise()`, `score_severity()`, `run_analysis()`, `ScoredEvent` dataclass |
| `writer/reporter.py` | `run_writer()`, `show_reports()`, `Report` dataclass, rich terminal output |
| `api/main.py` | FastAPI app, CORS, auto-pipeline scheduler |
| `api/routers/chat.py` | On-demand intel chatbot (DuckDuckGo + Groq) |
| `main.py` | CLI entry point — click groups wiring all agents |
| `config/sources.json` | Source URLs, params, alert filters |
| `config/.env` | `GROQ_API_KEY`, `DATABASE_URL`, `API_SECRET` — gitignored |
| `web/lib/api.ts` | Frontend API client with types |

## Code Conventions

- Type hints on all functions
- Dataclasses for all data structures
- `logging` module — `logger = logging.getLogger(__name__)`
- `click` + `rich` for CLI
- Every source subclasses `BaseSource` and implements `source_name`, `fetch()`, `health_check()`
- USGS GeoJSON coords: `[longitude, latitude, depth]` — `coords[0]`=lon, `coords[1]`=lat
- Groq JSON responses: `call_llm()` raises `LLMError` on failure — callers must handle it
- Dates: always store as ISO8601 UTC string; parse with `dateutil.parser.parse()`

## Database

PostgreSQL on Railway (`DATABASE_URL` in `config/.env`) with tables:
- `articles` — raw collected articles (`analyzed` flag)
- `scored_events` — Groq-scored events (`reported` flag)
- `reports` — generated crisis-comms reports (`printed` flag)
- `pipeline_state` — single-row table tracking running stages

## LLM

- Provider: Groq (via `groq` Python SDK)
- Model: `llama-3.3-70b-versatile` (temp=0 for analysis, temp=0.3 for writing)
- Chatbot: also Groq, same model
