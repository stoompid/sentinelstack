# SentinelStack TODOs

## TODO-1: gemini_rationale column rename (cosmetic)

**What:** The `scored_events` table has a column named `gemini_rationale` — the codebase uses Groq, not Gemini.

**Why:** Misleading for anyone reading the schema directly. Not user-facing.

**Fix:** `ALTER TABLE scored_events RENAME COLUMN gemini_rationale TO llm_rationale` + update all Python references. Low priority — column name is internal.

**Where:** `collector/store.py` (schema), `analyst/filter.py` (writes), `writer/reporter.py` (reads).
