from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import groupby
from typing import List

import io
import sys

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from analyst.llm import call_llm, configure_llm
from collector.store import get_conn

logger = logging.getLogger(__name__)

# Force UTF-8 stdout on Windows to handle non-ASCII characters in news content
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    _stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
else:
    _stdout = sys.stdout

console = Console(legacy_windows=False, file=_stdout)

MODEL = "gemini-2.5-flash"

TIER_COLORS = {
    "FLASH": "bold red",
    "PRIORITY": "bold yellow",
    "ROUTINE": "bold cyan",
}


@dataclass
class Report:
    report_id: str
    tier: str
    title: str
    situation: str
    impact: str
    action: str
    distro: str
    event_ids: str
    generated_at: datetime
    printed: bool = False


def _call_llm(prompt: str) -> dict:
    return call_llm(MODEL, prompt, temperature=0.3)


def _generate_report(events: list, tier: str) -> Report | None:
    events_text = "\n\n".join(
        f"Title: {e['title']}\nCountry: {e['country']}\nCategory: {e['category']}\n"
        f"Rationale: {e['gemini_rationale']}"
        for e in events
    )

    now = datetime.now(tz=timezone.utc)
    today_str = now.strftime(f"%A, %B {now.day}, %Y")  # e.g. "Saturday, March 14, 2026"

    # Tier 1=ROUTINE, Tier 2=PRIORITY, Tier 3=FLASH
    tier_num = {"FLASH": 3, "PRIORITY": 2, "ROUTINE": 1}.get(tier, 1)

    prompt = f"""You are a senior crisis communications analyst for a Global Security Operations Center (GSOC) at a major technology company. You support employee safety across corporate offices, data centers, and R&D labs worldwide.

Write a leadership intelligence report using ONLY the information provided. Your audience is VP-level security leadership who need to make decisions about employee safety and site security.

WRITING STANDARDS:
- Use probability language: "likely", "assessed", "appears", "may indicate"
- Never state uncertainties as confirmed facts
- Do NOT include numerical severity scores in prose
- Be concise and direct — no filler or repetition
- CRITICAL: Each section MUST meet the minimum sentence count

TODAY: {today_str}
ALERT TIER: {tier} (Tier {tier_num} of 3)
EVENTS:
{events_text}

Respond with JSON only. Follow the sentence counts exactly:
{{"title": "brief headline max 10 words", "situation": "MUST be 3-5 sentences. First sentence: On {today_str}, [what happened, where, scale — confirmed facts only]. Following sentences: regional context, escalation trajectory, prior incidents, confirmed casualties or infrastructure damage, government responses.", "impact": "MUST be 2-3 sentences. Focus ONLY on: (1) are employees in the affected area safe, (2) can they get to/from the office, (3) is travel to the region disrupted. Do NOT speculate about supply chains, semiconductors, or cloud infrastructure unless the event directly threatens them. Be specific about which offices or regions are affected.", "action": "MUST be 2-3 sentences. Specific executable GSOC actions: initiate employee accountability at [site], issue travel hold for [region], activate enhanced perimeter security, brief executive protection, coordinate with local LE, escalate to CMT if [trigger]."}}"""

    result = _call_llm(prompt)
    if not result or "title" not in result:
        return None

    return Report(
        report_id=str(uuid.uuid4()),
        tier=tier,
        title=result.get("title", "Intelligence Report"),
        situation=result.get("situation", ""),
        impact=result.get("impact", ""),
        action=result.get("action", ""),
        distro="",
        event_ids=",".join(e["event_id"] for e in events),
        generated_at=now,
    )


def _print_report(report: Report) -> None:
    color = TIER_COLORS.get(report.tier, "white")
    console.print(Rule(style=color))
    console.print(Text(f"[{report.tier}] — {report.title}", style=color))
    console.print(Rule(style=color))
    console.print(f"[bold]SITUATION:[/bold] {report.situation}\n")
    console.print(f"[bold]IMPACT:[/bold] {report.impact}\n")
    console.print(f"[bold]ACTION:[/bold] {report.action}\n")
    if report.distro:
        console.print(f"[bold]DISTRO:[/bold] [italic]{report.distro}[/italic]\n")
    console.print(f"[dim]Generated: {report.generated_at.strftime('%Y-%m-%dT%H:%MZ')}[/dim]\n")


def _load_unreported_events(conn, tier: str | None) -> list:
    cur = conn.cursor()
    if tier:
        cur.execute(
            "SELECT * FROM scored_events WHERE is_noise=0 AND reported=0 AND tier=%s ORDER BY severity DESC",
            (tier.upper(),),
        )
    else:
        cur.execute(
            "SELECT * FROM scored_events WHERE is_noise=0 AND reported=0 ORDER BY tier, severity DESC"
        )
    return cur.fetchall()


def _mark_reported(conn, event_ids: List[str]) -> None:
    cur = conn.cursor()
    cur.execute("UPDATE scored_events SET reported=1 WHERE event_id = ANY(%s)", (event_ids,))
    conn.commit()
    cur.close()


def _write_report(conn, report: Report) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reports
            (report_id, tier, title, situation, impact, action, distro, event_ids, generated_at, printed)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
        ON CONFLICT (report_id) DO UPDATE SET
            situation = EXCLUDED.situation,
            impact = EXCLUDED.impact,
            action = EXCLUDED.action,
            distro = EXCLUDED.distro
        """,
        (
            report.report_id, report.tier, report.title, report.situation,
            report.impact, report.action, report.distro, report.event_ids,
            report.generated_at.isoformat(),
        ),
    )
    conn.commit()
    cur.close()


def run_writer(api_key: str, tier: str | None = None) -> dict:
    configure_llm(api_key)
    conn = get_conn()
    events = _load_unreported_events(conn, tier)

    if not events:
        console.print("[dim]No unreported events found for the requested tier.[/dim]")
        conn.close()
        return {"reports_generated": 0}

    def group_key(e):
        return (e["tier"], e["country"] or "Unknown", e["category"] or "general")

    reports_generated = 0
    for key, group_iter in groupby(sorted(events, key=group_key), key=group_key):
        group = list(group_iter)
        report = _generate_report(group, key[0])
        if report is None:
            logger.warning(f"Failed to generate report for group {key}")
            continue
        _write_report(conn, report)
        _mark_reported(conn, [e["event_id"] for e in group])
        _print_report(report)
        reports_generated += 1

    conn.close()
    return {"reports_generated": reports_generated}


def show_reports(tier: str | None = None, limit: int = 20) -> None:
    conn = get_conn()
    cur = conn.cursor()
    if tier:
        cur.execute(
            "SELECT * FROM reports WHERE tier=%s ORDER BY generated_at DESC LIMIT %s",
            (tier.upper(), limit),
        )
    else:
        cur.execute("SELECT * FROM reports ORDER BY generated_at DESC LIMIT %s", (limit,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        console.print("[dim]No reports found.[/dim]")
        return

    for row in rows:
        _print_report(Report(
            report_id=row["report_id"], tier=row["tier"], title=row["title"],
            situation=row["situation"] or "", impact=row["impact"] or "",
            action=row["action"] or "", distro=row.get("distro") or "",
            event_ids=row["event_ids"] or "",
            generated_at=datetime.fromisoformat(row["generated_at"]),
        ))
