"""
Collector Agent CLI.

Usage:
    python -m collector.main collect --source [all|osac|reliefweb|usgs|nws|gdacs|rss_regional|gdelt]
    python -m collector.main health
"""

import json
import sys
from pathlib import Path
from typing import Dict, Type

import click
from rich.console import Console
from rich.spinner import Spinner
from rich.table import Table
from rich import print as rprint

from collector.sources.base import BaseSource
from collector.sources.osac import OSACSource
from collector.sources.reliefweb import ReliefWebSource
from collector.sources.usgs import USGSSource
from collector.sources.nws import NWSSource
from collector.sources.gdacs import GDACSSource
from collector.sources.rss_regional import RegionalRSSSource
from collector.sources.gdelt import GDELTSource
from collector.sources.gnews import GNewsSource
from collector.storage.sqlite_store import store_articles
from collector.storage.json_backup import write_backup
from collector.utils.retry import RetryExhausted
from collector.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)
console = Console()

SOURCES_CFG_PATH = Path(__file__).parents[1] / "config" / "sources.json"

SOURCE_CLASSES: Dict[str, Type[BaseSource]] = {
    "osac": OSACSource,
    "reliefweb": ReliefWebSource,
    "usgs": USGSSource,
    "nws": NWSSource,
    "gdacs": GDACSSource,
    "rss_regional": RegionalRSSSource,
    "gdelt": GDELTSource,
    "gnews": GNewsSource,
}


def load_sources_config() -> dict:
    return json.loads(SOURCES_CFG_PATH.read_text(encoding="utf-8"))


def build_source(key: str, cfg: dict) -> BaseSource:
    cls = SOURCE_CLASSES[key]
    return cls(cfg)


def run_source(key: str, source: BaseSource) -> dict:
    """Run a single source and return a status dict."""
    try:
        with console.status(f"[bold cyan]Fetching {source.name}…[/]", spinner="dots"):
            articles = source.fetch()
        new_count = store_articles(articles)
        write_backup(key, articles)
        return {"source": key, "name": source.name, "fetched": len(articles),
                "new": new_count, "status": "ok", "error": None}
    except RetryExhausted as exc:
        logger.error("source_retry_exhausted", source=key, error=str(exc))
        return {"source": key, "name": source.name, "fetched": 0,
                "new": 0, "status": "error", "error": str(exc)}
    except Exception as exc:
        logger.error("source_unexpected_error", source=key, error=str(exc))
        return {"source": key, "name": source.name, "fetched": 0,
                "new": 0, "status": "error", "error": str(exc)}


@click.group()
def cli():
    """SentinelStack Collector Agent."""
    setup_logging()


@cli.command()
@click.option(
    "--source",
    default="all",
    show_default=True,
    type=click.Choice(["all"] + list(SOURCE_CLASSES.keys()), case_sensitive=False),
    help="Source to collect from.",
)
def collect(source: str):
    """Fetch articles from one or all sources and store to SQLite + JSON backup."""
    cfg = load_sources_config()
    sources_cfg = cfg.get("sources", {})

    if source == "all":
        # Sort by priority ascending
        keys = sorted(
            [k for k in SOURCE_CLASSES if k in sources_cfg],
            key=lambda k: sources_cfg.get(k, {}).get("priority", 99),
        )
    else:
        keys = [source.lower()]

    results = []
    for key in keys:
        if key not in sources_cfg:
            console.print(f"[yellow]No config for source '{key}', skipping.[/]")
            continue
        src_cfg = sources_cfg[key]
        if not src_cfg.get("enabled", True):
            console.print(f"[dim]Source '{key}' is disabled, skipping.[/]")
            continue
        src = build_source(key, src_cfg)
        result = run_source(key, src)
        results.append(result)

    # Summary table
    table = Table(title="Collection Summary", show_header=True, header_style="bold magenta")
    table.add_column("Source", style="cyan")
    table.add_column("Fetched", justify="right")
    table.add_column("New", justify="right")
    table.add_column("Status")

    any_error = False
    for r in results:
        status_style = "green" if r["status"] == "ok" else "red"
        status_text = f"[{status_style}]{r['status']}[/{status_style}]"
        if r["error"]:
            status_text += f"  [dim red]{r['error'][:60]}[/]"
            any_error = True
        table.add_row(r["name"], str(r["fetched"]), str(r["new"]), status_text)

    console.print(table)
    sys.exit(1 if any_error else 0)


@cli.command()
def health():
    """Check connectivity for all enabled sources."""
    cfg = load_sources_config()
    sources_cfg = cfg.get("sources", {})

    table = Table(title="Source Health", show_header=True, header_style="bold magenta")
    table.add_column("Source", style="cyan")
    table.add_column("Status")

    any_down = False
    for key in sorted(SOURCE_CLASSES.keys()):
        if key not in sources_cfg:
            continue
        src_cfg = sources_cfg[key]
        if not src_cfg.get("enabled", True):
            table.add_row(src_cfg.get("name", key), "[dim]disabled[/]")
            continue
        src = build_source(key, src_cfg)
        with console.status(f"Checking {src.name}…", spinner="dots"):
            ok = src.health_check()
        if ok:
            table.add_row(src.name, "[green]healthy[/]")
        else:
            table.add_row(src.name, "[red]unreachable[/]")
            any_down = True

    console.print(table)
    sys.exit(1 if any_down else 0)


if __name__ == "__main__":
    cli()
