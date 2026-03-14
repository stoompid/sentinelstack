"""
Analyst Agent CLI.

Usage:
    python -m analyst.main --run       # score + write to sentinel_reports.db
    python -m analyst.main --dry-run   # show proximity scores without writing
"""

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from analyst.loader import load_unanalyzed, mark_analyzed
from analyst.deduplicator import deduplicate
from analyst.proximity import load_locations, score_proximity
from analyst.scorer import is_noise, score_severity
from analyst.models import ScoredEvent
from analyst.storage.analyst_store import store_scored_events
from collector.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)
console = Console()


def process_articles(dry_run: bool) -> int:
    """
    Run the full analyst pipeline.

    Returns count of events written (0 for dry-run).
    """
    articles = load_unanalyzed()
    if not articles:
        console.print("[yellow]No unanalyzed articles found.[/]")
        return 0

    console.print(f"[cyan]Loaded {len(articles)} unanalyzed articles.[/]")

    # Deduplicate
    articles = deduplicate(articles)
    console.print(f"[cyan]{len(articles)} articles after deduplication.[/]")

    locations = load_locations()
    scored_events = []
    analyzed_ids = []

    table = Table(
        title="Analyst Results",
        show_header=True,
        header_style="bold magenta",
        show_lines=False,
    )
    table.add_column("Title", max_width=50, no_wrap=True)
    table.add_column("Sev", justify="right", width=4)
    table.add_column("Noise", width=5)
    table.add_column("City", width=20)
    table.add_column("km", justify="right", width=7)
    table.add_column("Tier", width=9)

    for article in articles:
        with console.status(f"Scoring: {article.title[:60]}…", spinner="dots"):
            noise = is_noise(article)
            severity = 0 if noise else score_severity(article)

        proximity = None
        if article.event_latitude is not None and article.event_longitude is not None:
            proximity = score_proximity(article.event_latitude, article.event_longitude, locations)

        alert_tier = proximity.alert_tier if proximity else "none"
        city_id = proximity.city_id if proximity else None
        city_name = proximity.city_name if proximity else None
        distance_km = proximity.distance_km if proximity else None

        event = ScoredEvent(
            article_id=article.article_id,
            source_name=article.source_name,
            title=article.title,
            summary=article.summary,
            published_at=article.published_at.isoformat() if article.published_at else None,
            countries=json.dumps(article.countries),
            categories=json.dumps(article.categories),
            severity_score=severity,
            is_noise=noise,
            nearest_city_id=city_id,
            nearest_city_name=city_name,
            distance_km=distance_km,
            alert_tier=alert_tier,
        )
        scored_events.append(event)
        analyzed_ids.append(article.article_id)

        noise_str = "[red]yes[/]" if noise else "[green]no[/]"
        tier_color = {"flash": "red", "priority": "yellow", "routine": "blue", "none": "dim"}.get(alert_tier, "dim")
        table.add_row(
            article.title[:50],
            str(severity) if not noise else "-",
            noise_str,
            city_name or "-",
            f"{distance_km:.0f}" if distance_km else "-",
            f"[{tier_color}]{alert_tier}[/{tier_color}]",
        )

    console.print(table)

    if dry_run:
        console.print("[yellow]Dry-run mode: no data written.[/]")
        return 0

    new_count = store_scored_events(scored_events)
    mark_analyzed(analyzed_ids)
    console.print(f"[green]Stored {new_count} new scored events. Marked {len(analyzed_ids)} articles as analyzed.[/]")
    return new_count


@click.command()
@click.option("--run/--dry-run", "execute", default=False, help="Write results to DB (default: dry-run).")
def main(execute: bool):
    """Analyst Agent — score and proximity-rank unanalyzed articles."""
    setup_logging()
    count = process_articles(dry_run=not execute)
    sys.exit(0)


if __name__ == "__main__":
    main()
