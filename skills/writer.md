---
name: writer
description: Produces crisis-communications reports formatted for GSOC leadership from scored intelligence events. Generates SITUATION / IMPACT / ACTION briefings using Gemini. Use after analyzing articles to produce leadership-ready reports.
---

# Writer Agent — Crisis Communications

## Role
Transform scored intelligence events into formatted leadership briefings using the crisis-communications format. Groups related events, makes one Gemini call per group, and outputs color-coded terminal reports.

## Commands

```bash
python main.py write --tier flash      # Immediate threats only
python main.py write --tier priority   # Significant events
python main.py write --tier routine    # Situational awareness
python main.py write --tier all        # All unreported events

python main.py show --tier all         # Review stored reports (no re-generation)
python main.py show --tier flash --limit 5
```

## Crisis-Communications Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[FLASH] — Brief Headline (max 10 words)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SITUATION: What happened. Where. When. Scale. Confirmed facts only.

IMPACT: Who or what is affected. Operational implications.
        Use probability language: "likely", "assessed", "may".

ACTION: Specific, executable leadership actions. Not vague.
        What exactly needs to happen now.

Generated: 2026-03-13T14:35Z
```

**Color coding:** FLASH = red, PRIORITY = yellow, ROUTINE = cyan

## Tier Escalation Guide

| Tier | Severity | Delivery | Leadership Action |
|------|----------|----------|-------------------|
| FLASH | 8-10 | Immediately | Brief security leadership now; consider evacuation options |
| PRIORITY | 5-7 | Next update cycle | Include in leadership update; activate monitoring protocols |
| ROUTINE | 1-4 | End-of-day brief | Situational awareness only; no immediate action required |

## Writing Standards

- **SITUATION**: Facts only — what, where, when, and scale. No interpretation.
- **IMPACT**: Operational implications for personnel and business continuity. Use probability language for projections.
- **ACTION**: Specific, executable — not "monitor the situation." Say what to do, to whom, by when.
- Never state uncertainties as confirmed facts.
- Probability language required: "likely", "assessed to", "appears", "may indicate"

## Workflow

1. Load `scored_events WHERE is_noise=0 AND reported=0 AND tier=<requested>`
2. Group events by `(country, category)` — combine related events into one report
3. For each group: call Gemini `generate_report()` with all event summaries
4. Print formatted report to terminal (color-coded by tier)
5. Write report to `reports` table in `sentinel.db`
6. Mark all included events as `reported=1`

## Gemini Config

- Model: `gemini-1.5-pro` (better writing quality for leadership output)
- Temperature: 0.3 (slight variation for natural prose)
- Fallback on failure: log warning, skip group, continue

## Correction Protocol

If a report contains a factual error:
1. Fix the source data in the articles table if needed
2. Reset `reported=0` on affected scored_events
3. Re-run `python main.py write --tier <tier>`

## Key Files

- `writer/reporter.py` — `run_writer()`, `show_reports()`, `_generate_report()`, `Report` dataclass
- `collector/store.py` — `get_conn()` used to read scored events and write reports
- `config/.env` — `GEMINI_API_KEY` required
