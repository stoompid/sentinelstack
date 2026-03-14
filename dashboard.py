"""
SentinelStack — Streamlit Dashboard

Auto-runs the full Collector → Analyst → Reporter pipeline on startup
and refreshes every 15 minutes automatically.
"""

import sqlite3
import sys
import traceback
import threading
from datetime import datetime, timezone
from pathlib import Path

import json

import folium
from folium.plugins import MarkerCluster
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SentinelStack",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

RAW_DB = BASE_DIR / "data" / "raw" / "sentinel.db"
REPORTS_DB = BASE_DIR / "data" / "raw" / "sentinel_reports.db"

# ---------------------------------------------------------------------------
# Auto-refresh every 15 minutes (900,000 ms)
# ---------------------------------------------------------------------------
REFRESH_INTERVAL_MS = 15 * 60 * 1000
st_autorefresh(interval=REFRESH_INTERVAL_MS, key="pipeline_autorefresh")

# ---------------------------------------------------------------------------
# Pipeline imports (graceful degradation)
# ---------------------------------------------------------------------------
_import_errors: list[str] = []

try:
    from collector.main import load_sources_config, build_source, run_source
    _collector_ok = True
except Exception as _e:
    _collector_ok = False
    _import_errors.append(f"Collector: {_e}")

try:
    from analyst.main import process_articles
    _analyst_ok = True
except Exception as _e:
    _analyst_ok = False
    _import_errors.append(f"Analyst: {_e}")

try:
    from reporter.loader import load_unreported, mark_reported
    from reporter.grouper import group_events
    from reporter.writer import generate_report_sections
    from reporter.formatter import format_report
    from reporter.storage.report_store import store_report
    _reporter_ok = True
except Exception as _e:
    _reporter_ok = False
    _import_errors.append(f"Reporter: {_e}")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "pipeline_running" not in st.session_state:
    st.session_state.pipeline_running = False
if "last_run_time" not in st.session_state:
    st.session_state.last_run_time = None
if "last_run_results" not in st.session_state:
    st.session_state.last_run_results = []
if "pipeline_log" not in st.session_state:
    st.session_state.pipeline_log = []
if "auto_run_done" not in st.session_state:
    st.session_state.auto_run_done = False

SOURCE_PRIORITY = ["osac", "reliefweb", "usgs", "nws", "gdacs", "rss_regional", "gdelt"]

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect(db_path: Path):
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def _scalar(db_path: Path, sql: str, params: tuple = ()) -> int:
    conn = _connect(db_path)
    if conn is None:
        return 0
    try:
        val = conn.execute(sql, params).fetchone()
        return val[0] if val else 0
    finally:
        conn.close()

def _rows(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = _connect(db_path)
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

def get_metrics() -> dict:
    return {
        "total_articles": _scalar(RAW_DB, "SELECT COUNT(*) FROM raw_articles"),
        "unanalyzed": _scalar(RAW_DB, "SELECT COUNT(*) FROM raw_articles WHERE analyzed = 0"),
        "scored_events": _scalar(REPORTS_DB, "SELECT COUNT(*) FROM scored_events"),
        "reports_count": _scalar(REPORTS_DB, "SELECT COUNT(*) FROM reports"),
    }

# ---------------------------------------------------------------------------
# Tier display helpers
# ---------------------------------------------------------------------------
TIER_EMOJI = {"flash": "🔴", "priority": "🟡", "routine": "🔵", "none": "⚪"}
TIER_COLORS = {"flash": "#c0392b", "priority": "#d35400", "routine": "#2980b9", "none": "#7f8c8d"}

# ---------------------------------------------------------------------------
# Full automated pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(sources="all", log_fn=None):
    """
    Run Collect → Analyze → Report in sequence.
    log_fn(msg) is called with status updates.
    """
    def log(msg):
        ts = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        st.session_state.pipeline_log.append(full)
        if log_fn:
            log_fn(full)

    results = []

    # ── COLLECT ──────────────────────────────────────────────────────────
    if _collector_ok:
        log("Starting collection…")
        try:
            cfg = load_sources_config()
            sources_cfg = cfg.get("sources", {})
            keys = sorted(
                [k for k in SOURCE_PRIORITY if k in sources_cfg],
                key=lambda k: sources_cfg.get(k, {}).get("priority", 99),
            )
            for key in keys:
                src_cfg = sources_cfg[key]
                if not src_cfg.get("enabled", True):
                    log(f"  ↷ {key} disabled, skipping")
                    continue
                log(f"  ↓ Fetching {key}…")
                try:
                    src = build_source(key, src_cfg)
                    result = run_source(key, src)
                    results.append(result)
                    log(f"  ✓ {key}: {result['fetched']} fetched, {result['new']} new")
                except Exception as exc:
                    log(f"  ✗ {key} error: {exc}")
                    results.append({"source": key, "name": key, "fetched": 0, "new": 0, "status": "error", "error": str(exc)})
        except Exception as exc:
            log(f"Collection failed: {exc}")
    else:
        log("⚠️ Collector unavailable — skipping")

    # ── ANALYZE ──────────────────────────────────────────────────────────
    if _analyst_ok:
        log("Running analysis…")
        try:
            count = process_articles(dry_run=False)
            log(f"  ✓ Analysis complete — {count} new scored events")
        except Exception as exc:
            log(f"  ✗ Analysis error: {exc}")
    else:
        log("⚠️ Analyst unavailable — skipping")

    # ── REPORT ───────────────────────────────────────────────────────────
    if _reporter_ok:
        log("Generating reports…")
        try:
            events = load_unreported(tier="all")
            if events:
                groups = group_events(events)
                reported_ids = []
                for group in groups:
                    sections = generate_report_sections(group)
                    report_text = format_report(group, sections)
                    lead = group[0]
                    event_ids = [e["event_id"] for e in group]
                    store_report(event_ids, lead.get("alert_tier", "none"), lead.get("title", ""), report_text)
                    reported_ids.extend(event_ids)
                mark_reported(reported_ids)
                log(f"  ✓ {len(groups)} report(s) generated")
            else:
                log("  ℹ No unreported events to report")
        except Exception as exc:
            log(f"  ✗ Reporter error: {exc}")
    else:
        log("⚠️ Reporter unavailable — skipping")

    st.session_state.last_run_results = results
    st.session_state.last_run_time = datetime.now(tz=timezone.utc)
    st.session_state.pipeline_running = False
    log("Pipeline complete.")

# ---------------------------------------------------------------------------
# Auto-run on first load (or each 15-min refresh)
# ---------------------------------------------------------------------------
if not st.session_state.auto_run_done and not st.session_state.pipeline_running:
    st.session_state.pipeline_running = True
    st.session_state.auto_run_done = True
    # Run in background thread so Streamlit doesn't block
    t = threading.Thread(target=run_full_pipeline, daemon=True)
    t.start()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar():
    st.sidebar.title("🛰️ SentinelStack")

    # Pipeline status
    if st.session_state.pipeline_running:
        st.sidebar.status("Pipeline running…", state="running")
    elif st.session_state.last_run_time:
        last = st.session_state.last_run_time.strftime("%H:%M UTC")
        st.sidebar.success(f"Last run: {last}")

    st.sidebar.markdown("---")

    # Manual trigger
    st.sidebar.subheader("⚡ Manual Run")
    if st.sidebar.button("Run Pipeline Now", use_container_width=True, type="primary",
                         disabled=st.session_state.pipeline_running):
        st.session_state.pipeline_running = True
        t = threading.Thread(target=run_full_pipeline, daemon=True)
        t.start()
        st.rerun()

    st.sidebar.caption("Auto-refreshes every 15 min")
    st.sidebar.markdown("---")

    # Per-source manual collect
    st.sidebar.subheader("📡 Collect Single Source")
    selected_source = st.sidebar.selectbox("Source", SOURCE_PRIORITY)
    if st.sidebar.button("Collect", use_container_width=True,
                         disabled=st.session_state.pipeline_running):
        if _collector_ok:
            with st.spinner(f"Fetching {selected_source}…"):
                try:
                    cfg = load_sources_config()
                    src_cfg = cfg["sources"][selected_source]
                    src = build_source(selected_source, src_cfg)
                    result = run_source(selected_source, src)
                    st.sidebar.success(f"{result['new']} new articles from {selected_source}")
                except Exception as exc:
                    st.sidebar.error(str(exc))

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Refresh View", use_container_width=True):
        st.rerun()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def render_overview():
    st.header("Overview")
    m = get_metrics()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Articles", m["total_articles"])
    c2.metric("Unanalyzed", m["unanalyzed"])
    c3.metric("Scored Events", m["scored_events"])
    c4.metric("Reports", m["reports_count"])

    st.markdown("---")

    # Pipeline log
    if st.session_state.pipeline_log:
        st.subheader("Pipeline Log")
        log_text = "\n".join(st.session_state.pipeline_log[-40:])  # last 40 lines
        st.code(log_text, language=None)
        if st.button("Clear Log"):
            st.session_state.pipeline_log = []
            st.rerun()
        st.markdown("---")

    st.subheader("Recent Articles")
    rows = _rows(RAW_DB, "SELECT source_name, title, collected_at FROM raw_articles ORDER BY collected_at DESC LIMIT 10")
    if not rows:
        st.info("No data yet — pipeline is running, check back in a moment.")
        return
    import pandas as pd
    df = pd.DataFrame(rows)
    df["title"] = df["title"].str[:70]
    df.columns = ["Source", "Title", "Collected At"]
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_articles():
    st.header("Articles")
    conn = _connect(RAW_DB)
    if conn is None:
        st.info("No data yet — pipeline is running.")
        return
    try:
        source_names = [r[0] for r in conn.execute("SELECT DISTINCT source_name FROM raw_articles ORDER BY source_name").fetchall()]
    finally:
        conn.close()

    c1, c2, c3 = st.columns([2, 3, 3])
    source_filter = c1.selectbox("Source", ["All"] + source_names)
    date_range = c2.date_input("Date range", value=[])
    title_search = c3.text_input("Search title", placeholder="keyword…")

    conditions, params = [], []
    if source_filter != "All":
        conditions.append("source_name = ?"); params.append(source_filter)
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        conditions.append("DATE(published_at) BETWEEN ? AND ?")
        params += [str(date_range[0]), str(date_range[1])]
    if title_search.strip():
        conditions.append("title LIKE ?"); params.append(f"%{title_search.strip()}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = _rows(RAW_DB, f"SELECT source_name, title, published_at, countries, categories, analyzed, event_latitude, event_longitude FROM raw_articles {where} ORDER BY collected_at DESC LIMIT 500", tuple(params))

    if not rows:
        st.info("No articles match the filters.")
        return

    import pandas as pd
    df = pd.DataFrame(rows)
    df["title"] = df["title"].str[:70]
    df["analyzed"] = df["analyzed"].map({1: "✅", 0: "⏳"})
    df["coords"] = df.apply(lambda r: "📍" if r["event_latitude"] is not None else "", axis=1)
    df = df.drop(columns=["event_latitude", "event_longitude"])
    df.columns = ["Source", "Title", "Published At", "Countries", "Categories", "Analyzed", "Geo"]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} article(s) shown")


def render_scored_events():
    st.header("Scored Events")
    if not REPORTS_DB.exists():
        st.info("No scored events yet — pipeline is running.")
        return

    c1, c2 = st.columns([2, 3])
    tier_filter = c1.selectbox("Alert Tier", ["all", "flash", "priority", "routine"], key="ev_tier")
    min_sev = c2.slider("Min severity", 1, 10, 1)

    conditions = ["severity_score >= ?"]
    params: list = [min_sev]
    if tier_filter != "all":
        conditions.append("alert_tier = ?"); params.append(tier_filter)

    rows = _rows(REPORTS_DB, f"SELECT title, source_name, severity_score, alert_tier, nearest_city_name, distance_km, is_noise FROM scored_events WHERE {' AND '.join(conditions)} ORDER BY severity_score DESC LIMIT 500", tuple(params))

    if not rows:
        st.info("No events match the filters.")
        return

    import pandas as pd
    df = pd.DataFrame(rows)
    df["title"] = df["title"].str[:70]
    df["is_noise"] = df["is_noise"].map({1: "🔇 Yes", 0: "✅ No"})
    df["distance_km"] = df["distance_km"].apply(lambda v: f"{v:.0f} km" if v is not None else "—")
    df["nearest_city_name"] = df["nearest_city_name"].fillna("—")
    df["alert_tier"] = df["alert_tier"].apply(lambda t: f"{TIER_EMOJI.get(t,'')} {t.upper()}")
    df.columns = ["Title", "Source", "Severity", "Tier", "Nearest City", "Distance", "Noise"]
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} event(s) shown")


def render_map():
    st.header("Asset Map")

    LOCATIONS_PATH = BASE_DIR / "config" / "locations.json"
    locations = json.loads(LOCATIONS_PATH.read_text(encoding="utf-8")).get("locations", [])

    # Priority → marker colour
    PRIORITY_COLOR = {
        "critical": "red",
        "high":     "orange",
        "medium":   "blue",
        "low":      "gray",
    }

    # Build base map centred on world view
    m = folium.Map(
        location=[20, 10],
        zoom_start=2,
        tiles="CartoDB positron",   # clean, Google Maps-like light theme
        control_scale=True,
    )

    # ── Watchlist city layer ───────────────────────────────────────────
    city_group = folium.FeatureGroup(name="🏢 Watchlist Cities", show=True)
    for loc in locations:
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is None or lon is None:
            continue
        priority = loc.get("priority", "medium")
        color = PRIORITY_COLOR.get(priority, "blue")
        popup_html = f"""
            <b>{loc['name']}</b><br>
            {loc['city']}, {loc['country']}<br>
            <i>Priority: <b style='color:{color}'>{priority.upper()}</b></i><br>
            <small>{loc.get('notes','')}</small>
        """
        folium.CircleMarker(
            location=[lat, lon],
            radius=10 if priority == "critical" else 8 if priority == "high" else 6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{loc['city']} [{priority.upper()}]",
        ).add_to(city_group)
    city_group.add_to(m)

    # ── Live events layer (from SQLite — anything with coords) ─────────
    event_rows = _rows(
        RAW_DB,
        """
        SELECT title, source_name, summary, event_latitude, event_longitude,
               event_magnitude, categories, published_at
        FROM raw_articles
        WHERE event_latitude IS NOT NULL
        ORDER BY collected_at DESC
        LIMIT 300
        """,
    )

    if event_rows:
        event_cluster = MarkerCluster(name="⚠️ Live Events", show=True)
        for row in event_rows:
            lat, lon = row["event_latitude"], row["event_longitude"]
            mag = row.get("event_magnitude")
            source = row.get("source_name", "")
            title = row.get("title", "")[:80]
            summary = row.get("summary", "")[:120]
            pub = row.get("published_at", "")

            # Colour by source type
            if "USGS" in source or "Earthquake" in source:
                icon_color = "darkred"
                icon = "warning-sign"
            elif "Weather" in source or "NWS" in source:
                icon_color = "darkblue"
                icon = "cloud"
            else:
                icon_color = "darkpurple"
                icon = "info-sign"

            mag_str = f"<br>Magnitude: <b>{mag:.1f}</b>" if mag else ""
            popup_html = f"""
                <b>{title}</b><br>
                <i>{source}</i>{mag_str}<br>
                {summary}<br>
                <small>{pub}</small>
            """
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=title,
                icon=folium.Icon(color=icon_color, icon=icon, prefix="glyphicon"),
            ).add_to(event_cluster)
        event_cluster.add_to(m)

    # ── Proximity rings for critical cities ───────────────────────────
    ring_group = folium.FeatureGroup(name="📏 Alert Rings (critical only)", show=False)
    for loc in locations:
        if loc.get("priority") != "critical":
            continue
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if lat is None:
            continue
        # Flash 50km, Priority 200km, Routine 500km
        for km, color, dash in [(50, "red", "5,5"), (200, "orange", "8,4"), (500, "blue", "3,6")]:
            folium.Circle(
                location=[lat, lon],
                radius=km * 1000,
                color=color,
                weight=1,
                fill=False,
                dash_array=dash,
                tooltip=f"{loc['city']} — {km} km",
            ).add_to(ring_group)
    ring_group.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # ── Legend ─────────────────────────────────────────────────────────
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:12px 16px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.3);font-size:13px;">
        <b>Watchlist Cities</b><br>
        🔴 Critical &nbsp; 🟠 High &nbsp; 🔵 Medium<br><br>
        <b>Live Events</b><br>
        🔴 Earthquake &nbsp; 🔵 Weather &nbsp; 🟣 Other<br><br>
        <b>Alert Rings</b> (critical cities)<br>
        <span style='color:red'>— 50 km Flash</span><br>
        <span style='color:orange'>— 200 km Priority</span><br>
        <span style='color:blue'>— 500 km Routine</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Render
    event_count = len(event_rows)
    col1, col2, col3 = st.columns(3)
    col1.metric("Watchlist Cities", len(locations))
    col2.metric("Live Events on Map", event_count)
    col3.metric("Critical Sites", sum(1 for l in locations if l.get("priority") == "critical"))

    st.caption("Toggle layers top-right · Click markers for details · Rings show Flash/Priority/Routine proximity zones")

    st_folium(m, use_container_width=True, height=620, returned_objects=[])


def render_reports():
    st.header("Intelligence Reports")
    if not REPORTS_DB.exists():
        st.info("No reports yet — pipeline is running.")
        return

    tier_filter = st.selectbox("Filter by tier", ["all", "flash", "priority", "routine"], key="rpt_tier")
    if tier_filter == "all":
        rows = _rows(REPORTS_DB, "SELECT report_id, alert_tier, title, report_text, generated_at FROM reports ORDER BY generated_at DESC")
    else:
        rows = _rows(REPORTS_DB, "SELECT report_id, alert_tier, title, report_text, generated_at FROM reports WHERE alert_tier = ? ORDER BY generated_at DESC", (tier_filter,))

    if not rows:
        st.info("No reports found.")
        return

    st.markdown(f"**{len(rows)} report(s)**")
    for row in rows:
        tier = row.get("alert_tier", "none")
        emoji = TIER_EMOJI.get(tier, "⚪")
        label = f"{emoji} [{tier.upper()}]  {row.get('title', 'Untitled')}"
        with st.expander(label, expanded=(tier == "flash")):
            st.caption(f"Generated: {row.get('generated_at', '')}  ·  ID: {row.get('report_id', '')[:8]}…")
            st.markdown("---")
            st.markdown(row.get("report_text", ""))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    render_sidebar()

    if _import_errors:
        with st.expander("⚠️ Import warnings", expanded=False):
            for e in _import_errors:
                st.warning(e)

    if st.session_state.pipeline_running:
        st.info("⏳ Pipeline is currently running — data will appear here shortly. This page refreshes automatically.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "🗺️ Map", "Articles", "Scored Events", "Reports"])
    with tab1: render_overview()
    with tab2: render_map()
    with tab3: render_articles()
    with tab4: render_scored_events()
    with tab5: render_reports()


if __name__ == "__main__":
    main()
