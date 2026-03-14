# SentinelStack TODOs

## TODO-1: LLM failure silent default (noise=False)

**What:** When Groq returns `{}` (timeout, bad JSON, API error), `is_noise()` in `analyst/filter.py:72`
defaults to `False` — treating the failed article as a real event scored at severity 3.

**Why:** A Groq outage silently pumps ROUTINE-tier garbage into `scored_events` and generates
junk reports. Over time this pollutes the reports table.

**Pros:** Fix prevents report pollution during LLM outages.
**Cons:** Flipping default to `True` would drop real events — also wrong. Needs a 3rd state.

**Context:** The right fix is an explicit error signal from `_call_llm()` — return a sentinel
like `{"_llm_error": True}` or raise a typed exception. Then `run_analysis()` detects the
error and skips the article (marks `analyzed=1` without writing to `scored_events`).
Natural place to implement this is the shared `llm.py` extracted in Issue 6.

**Where to start:** `analyst/filter.py:56-72` (`is_noise`), `analyst/filter.py:112` (`run_analysis`).

**Depends on:** Issue 6 (extract shared `llm.py`) should be done first.

---

## TODO-2: bulk_insert() transaction rollback

**What:** `bulk_insert()` in `collector/store.py:135` has no transaction wrapping. A DB failure
mid-batch leaves some articles partially written with inaccurate new/skipped counts.

**Why:** Silent partial state makes debugging hard. A retry on the same batch will hit
ON CONFLICT DO NOTHING for already-inserted rows (safe), but the returned counts from
the failed run are wrong — could mislead monitoring.

**Pros:** Atomic inserts; new/skipped counts always accurate; consistent DB state.
**Cons:** On failure the whole batch rolls back — re-collect on next run.

**Context:** `psycopg2` connections default to `autocommit=False`. After the Issue 7 single-connection
fix, add `try/except` with `conn.rollback()` in the except block and `conn.commit()` once
at the end. ~5 line change on top of Issue 7.

**Where to start:** `collector/store.py:135` after Issue 7 is merged.

**Depends on:** Issue 7 (single connection in bulk_insert) must be done first.

---

## TODO-3: CLAUDE.md drift — Gemini references

**What:** `sentinelstack/CLAUDE.md` references "Gemini" throughout (is_noise Gemini call,
scorer.py, gemini_rationale column). The codebase uses Groq everywhere.

**Why:** Stale docs mislead Claude Code and future contributors about the actual LLM provider.
The `gemini_rationale` column name in `scored_events` is also technically a lie.

**Pros:** 10-minute fix. No code changes needed (just docs). Prevents confusion.
**Cons:** Column rename (`gemini_rationale` → `llm_rationale`) requires a DB migration —
do separately if desired.

**Context:** Update CLAUDE.md to say Groq (llama-3.3-70b-versatile) everywhere Gemini appears.
Column rename is optional — field name is internal to the DB, not surfaced in reports.

**Where to start:** `sentinelstack/CLAUDE.md` — search/replace Gemini → Groq.
