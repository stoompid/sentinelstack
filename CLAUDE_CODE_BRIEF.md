# SentinelStack - Claude Code Project Brief

## What This Is
SentinelStack is a personal multi-agent threat intelligence tool for a GSOC (Global Security Operations Center) analyst. Focus is **geopolitical and physical threat intelligence** — civil unrest, conflict escalation, weather events, executive travel risk. NOT cyber (though cyber adjacency may be added later).

## Owner Context
- Vincent, 23, GSOC Analyst at Sony Interactive Entertainment (ending April 2025)
- Based in San Jose, CA
- Background: B.S. Technology & Information Management from UCSC, CTF competitor, geopolitical analysis focus
- Target career: Federal national security/intelligence roles (HSI, NSA, CIA)

## Tech Stack (Confirmed)
- **Python** in WSL2 on Windows
- **Gemini API** as the AI brain (key already stored in `config/.env`)
- **Free data sources**: OSAC RSS, ReliefWeb API, regional news RSS, GDELT
- **Local dev**: ThinkPad X1 Carbon Gen 13
- **Future deployment**: Oracle Free Tier

## Architecture — Three Agents

### 1. Collector Agent (BUILD THIS FIRST — partially complete)
- Scrapes sources on manual trigger (event-driven, not scheduled)
- Dumps raw data to SQLite (primary) + JSON backup
- **No deduplication** — that's handled by Analyst Agent
- Retry logic: 3x with exponential backoff, then skip

### 2. Analyst Agent (BUILD SECOND)
- Reads raw data, filters noise via Gemini
- Scores by severity and proximity to location watchlist
- Handles deduplication across sources
- Country/region-level granularity (not city-level)

### 3. Reporter Agent (BUILD THIRD)
- Auto-drafts finished intelligence reports
- Format: **Situation / Impact / Action** structure
- Tiers: Routine / Priority / Flash
- Style: Continuous prose, NO bullet points in analyst comments, probability language

## Data Source Priority (in order)
1. **OSAC RSS** — curated, low noise
2. **ReliefWeb API** — humanitarian focus
3. **Regional news RSS** — East Asia, Middle East, Latin America, Europe
4. **GDELT** — highest volume, use last

## Key Configuration Files (already created)
- `config/.env` — Gemini API key (gitignored)
- `config/locations.json` — 25 global corporate watchlist cities (SF, Tokyo, London, Taipei, Dubai, São Paulo, etc.)
- `config/sources.json` — RSS URLs and API endpoints for all sources

## Output Format Requirements
- **Continuous prose** — no bullet points in analyst comment blocks
- **Situation / Impact / Action** structure for reports
- **Probability language** in assessments ("likely," "probably," "assessed with moderate confidence")
- Tiers: Routine (FYI), Priority (action within 24h), Flash (immediate)

## Current State
The Collector Agent is **partially built**. Files created so far:
```
sentinelstack/
├── collector/
│   ├── __init__.py ✓
│   ├── sources/
│   │   ├── base.py ✓ (complete)
│   │   ├── osac.py (INCOMPLETE — cut off mid-file)
│   │   ├── reliefweb.py (not started)
│   │   ├── gdelt.py (not started)
│   │   └── rss_regional.py (not started)
│   ├── storage/
│   │   ├── sqlite_store.py (not started)
│   │   └── json_backup.py (not started)
│   └── utils/
│       ├── __init__.py ✓
│       ├── retry.py ✓ (complete)
│       └── logging.py ✓ (complete)
├── config/
│   ├── .env ✓
│   ├── locations.json ✓
│   └── sources.json ✓
├── data/
│   └── raw/
├── requirements.txt ✓
└── .gitignore ✓
```

## Next Steps for Claude Code
1. **Complete `osac.py`** — the file was cut off mid-function
2. **Build `reliefweb.py`** — ReliefWeb API client
3. **Build `rss_regional.py`** — handles all 4 regional RSS bundles
4. **Build `gdelt.py`** — GDELT API client (lowest priority)
5. **Build `sqlite_store.py`** — primary storage
6. **Build `json_backup.py`** — JSON backup writer
7. **Build `collector/main.py`** — CLI entry point with Click
8. **Test the full pipeline** with `python -m collector.main --source all`

## Telegram Module
- **Not in initial build** — make it pluggable for later
- Will need Telegram API credentials when ready

## Commands to Use
```bash
# Run all sources
python -m collector.main --source all

# Run single source
python -m collector.main --source osac
python -m collector.main --source reliefweb

# Health check
python -m collector.main --health
```

## Style Notes
- Use `structlog` for logging (already configured)
- Use `click` + `rich` for CLI
- Type hints everywhere
- Dataclasses for data structures
- Keep functions focused and testable
