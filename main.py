#!/usr/bin/env python3
"""SentinelStack — GSOC multi-agent threat intelligence CLI."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import click
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv(Path(__file__).parent / "config" / ".env")

console = Console()
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def _get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        console.print("[red]Error:[/red] GROQ_API_KEY not set in config/.env")
        sys.exit(1)
    return key


def _load_sources_config() -> dict:
    path = Path(__file__).parent / "config" / "sources.json"
    with open(path) as f:
        return json.load(f)


def _build_source(name: str, config: dict):
    from collector.base import build_source
    return build_source(name, config)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """SentinelStack — geopolitical & physical threat intelligence for GSOC analysts."""


@cli.command()
@click.option(
    "--source",
    default="all",
    type=click.Choice(["all", "un_news", "bbc", "usgs", "gdacs", "nws"], case_sensitive=False),
    show_default=True,
    help="Source to collect from.",
)
def collect(source: str):
    """Collect articles from OSINT sources."""
    from collector.store import init_db, bulk_insert

    init_db()
    sources_cfg = _load_sources_config()

    # Priority order
    priority_order = ["un_news", "bbc", "usgs", "gdacs", "nws"]
    targets = priority_order if source == "all" else [source.lower()]

    table = Table(title="Collection Summary", show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Status")

    for name in targets:
        cfg = sources_cfg.get(name, {})
        if not cfg.get("enabled", True):
            table.add_row(name, "-", "-", "-", "[dim]disabled[/dim]")
            continue
        try:
            src = _build_source(name, cfg)
            articles = src.fetch()
            new, skipped = bulk_insert(articles)
            table.add_row(
                name,
                str(len(articles)),
                f"[green]{new}[/green]",
                str(skipped),
                "[green]OK[/green]",
            )
        except Exception as e:
            table.add_row(name, "-", "-", "-", f"[red]ERROR: {e}[/red]")

    console.print(table)


@cli.command()
@click.option("--dry-run", is_flag=True, help="Score articles without writing to DB.")
def analyze(dry_run: bool):
    """Analyze collected articles — filter noise and score severity."""
    from analyst.filter import run_analysis
    from collector.store import init_db

    init_db()
    api_key = _get_api_key()

    if dry_run:
        console.print("[yellow]Dry-run mode — scores will not be saved.[/yellow]")

    with console.status("Analyzing articles with Gemini..."):
        summary = run_analysis(api_key=api_key, dry_run=dry_run)

    table = Table(title="Analysis Summary", show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("Scored", str(summary["analyzed"]))
    table.add_row("Noise filtered", str(summary["noise"]))
    table.add_row("[bold red]FLASH[/bold red]", str(summary["flash"]))
    table.add_row("[bold yellow]PRIORITY[/bold yellow]", str(summary["priority"]))
    table.add_row("[bold cyan]ROUTINE[/bold cyan]", str(summary["routine"]))
    console.print(table)


@cli.command()
@click.option(
    "--tier",
    required=True,
    type=click.Choice(["flash", "priority", "routine", "all"], case_sensitive=False),
    help="Alert tier to write reports for.",
)
def write(tier: str):
    """Generate crisis-communications reports for leadership."""
    from writer.reporter import run_writer
    from collector.store import init_db

    init_db()
    api_key = _get_api_key()
    tier_arg = None if tier.lower() == "all" else tier.upper()

    with console.status(f"Generating {tier.upper()} reports..."):
        result = run_writer(api_key=api_key, tier=tier_arg)

    console.print(f"\n[green]{result['reports_generated']} report(s) generated.[/green]")


@cli.command()
@click.option(
    "--tier",
    default="all",
    type=click.Choice(["flash", "priority", "routine", "all"], case_sensitive=False),
    show_default=True,
    help="Filter by tier.",
)
@click.option("--limit", default=20, show_default=True, help="Max reports to show.")
def show(tier: str, limit: int):
    """Show previously generated reports."""
    from writer.reporter import show_reports
    from collector.store import init_db

    init_db()
    tier_arg = None if tier.lower() == "all" else tier.upper()
    show_reports(tier=tier_arg, limit=limit)


@cli.command()
def health():
    """Check connectivity for all configured sources."""
    sources_cfg = _load_sources_config()
    priority_order = ["un_news", "bbc", "usgs", "gdacs", "nws"]

    table = Table(title="Source Health", show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Latency")

    for name in priority_order:
        cfg = sources_cfg.get(name, {})
        if not cfg.get("enabled", True):
            table.add_row(name, "[dim]disabled[/dim]", "-")
            continue
        try:
            import time
            src = _build_source(name, cfg)
            t0 = time.perf_counter()
            ok = src.health_check()
            latency = f"{(time.perf_counter() - t0) * 1000:.0f}ms"
            status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
            table.add_row(name, status, latency)
        except Exception as e:
            table.add_row(name, f"[red]ERROR[/red]", "-")

    console.print(table)


if __name__ == "__main__":
    cli()
