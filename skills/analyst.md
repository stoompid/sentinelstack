---
name: analyst
description: Scores raw collected articles for threat relevance and severity using Gemini. Filters noise, assigns FLASH/PRIORITY/ROUTINE tiers, and writes scored events to sentinel.db. Use after collecting articles to triage intelligence before writing reports.
---

# Analyst Agent

## Role
Triage layer between Collector and Writer. Loads unanalyzed articles, filters noise with Gemini, scores severity 1-10, assigns alert tiers, and writes `scored_events` to `data/sentinel.db`.

## Commands

```bash
python main.py analyze              # Score and write to DB
python main.py analyze --dry-run   # Score and print only, no DB writes
```

## Workflow

1. Load all `articles WHERE analyzed=0` from `sentinel.db`
2. For each article:
   a. **Dedup check** — skip if `content_hash` seen in `scored_events` within last 24h
   b. **Noise filter** — call Gemini `is_noise()` prompt; if noise, mark `analyzed=1`, skip
   c. **Severity score** — call Gemini `score_severity()` prompt; get int 1-10 + rationale
   d. **Tier assignment** — hard rules (not Gemini): 8-10=FLASH, 5-7=PRIORITY, 1-4=ROUTINE
   e. Write `ScoredEvent` to `scored_events` table
   f. Mark `articles.analyzed=1`
3. Print summary: scored | noise filtered | FLASH | PRIORITY | ROUTINE

## Tier Rules (authoritative)

| Severity | Tier | Meaning |
|----------|------|---------|
| 8-10 | FLASH | Immediate threat — brief leadership now |
| 5-7 | PRIORITY | Significant — include in next leadership update |
| 1-4 | ROUTINE | Situational awareness — end-of-day brief |

## Noise Filter

**NOISE** = routine politics, economics, sports, entertainment, minor weather, stock markets, product launches, celebrity news.

**NOT NOISE** = civil unrest, protests, riots, conflict escalation, terrorist attacks, coups, sanctions with operational impact, evacuations, natural disasters, seismic events, leadership travel risk.

## Deduplication

- Same `content_hash` within 24h = duplicate → skip, mark analyzed
- Cross-source dedup is intentional: earthquake + humanitarian response to same event are different events
- Do NOT deduplicate across different event types in the same country

## Gemini Config

- Model: `gemini-1.5-flash` (fast, cheap for classification)
- Temperature: 0 (deterministic)
- Fallback on parse failure: `severity=3, tier=ROUTINE, is_noise=False`

## Key Files

- `analyst/filter.py` — `is_noise()`, `score_severity()`, `run_analysis()`, `ScoredEvent` dataclass
- `collector/store.py` — `get_conn()` used to read articles and write scored events
- `config/.env` — `GEMINI_API_KEY` required
