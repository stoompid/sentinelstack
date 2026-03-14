"""
Reporter Agent CLI.

Usage:
    python -m reporter.main --tier [all|flash|priority|routine]
"""

import sys

import click
from rich.console import Console
from rich.panel import Panel

from reporter.loader import load_unreported, mark_reported
from reporter.grouper import group_events
from reporter.writer import generate_report_sections
from reporter.formatter import format_report
from reporter.storage.report_store import store_report
from collector.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)
console = Console()

TIER_STYLES = {
    "flash": "bold red",
    "priority": "bold yellow",
    "routine": "bold blue",
    "none": "dim",
}


@click.command()
@click.option(
    "--tier",
    default="all",
    show_default=True,
    type=click.Choice(["all", "flash", "priority", "routine"], case_sensitive=False),
    help="Alert tier to report on.",
)
def main(tier: str):
    """Reporter Agent — draft intelligence reports from scored events."""
    setup_logging()

    events = load_unreported(tier=tier)
    if not events:
        console.print(f"[yellow]No unreported events for tier '{tier}'.[/]")
        sys.exit(0)

    console.print(f"[cyan]Loaded {len(events)} unreported events (tier={tier}).[/]")
    groups = group_events(events)
    console.print(f"[cyan]Grouped into {len(groups)} report(s).[/]")

    reported_event_ids = []

    for group in groups:
        with console.status(f"Drafting report for: {group[0].get('title', '')[:60]}…", spinner="dots"):
            sections = generate_report_sections(group)

        report_text = format_report(group, sections)
        lead = group[0]
        alert_tier = lead.get("alert_tier", "none")
        title = lead.get("title", "")
        event_ids = [e["event_id"] for e in group]

        # Print to console
        style = TIER_STYLES.get(alert_tier, "")
        console.print(Panel(report_text, style=style, expand=False))

        # Persist
        store_report(event_ids, alert_tier, title, report_text)
        reported_event_ids.extend(event_ids)

    mark_reported(reported_event_ids)
    console.print(f"[green]Generated {len(groups)} report(s). Marked {len(reported_event_ids)} events as reported.[/]")
    sys.exit(0)


if __name__ == "__main__":
    main()
