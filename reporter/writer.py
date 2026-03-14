"""
Gemini report writer.

One API call per report group → JSON with situation/impact/action keys.
"""

import json
import os
from pathlib import Path
from typing import List

import google.generativeai as genai
from dotenv import load_dotenv

from collector.utils.logging import get_logger

logger = get_logger(__name__)

ENV_PATH = Path(__file__).parents[1] / "config" / ".env"
load_dotenv(ENV_PATH)

_model = None


def _get_model():
    global _model
    if _model is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set in config/.env")
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel("gemini-1.5-flash")
    return _model


def generate_report_sections(events: List[dict]) -> dict:
    """
    Call Gemini once for a group of events and return situation/impact/action.

    Returns dict with keys: situation, impact, action.
    Falls back to placeholder text on API error.
    """
    model = _get_model()

    # Build a brief digest for Gemini
    items = []
    for e in events:
        items.append(
            f"- [{e.get('source_name', '')}] {e.get('title', '')} "
            f"(severity {e.get('severity_score', '?')}/10): {e.get('summary', '')[:300]}"
        )
    digest = "\n".join(items)

    nearest_city = events[0].get("nearest_city_name") if events else None
    distance_km = events[0].get("distance_km") if events else None
    proximity_str = (
        f"Nearest watchlist city: {nearest_city} ({distance_km:.0f} km)"
        if nearest_city and distance_km else "No watchlist city proximity data."
    )

    prompt = (
        "You are a GSOC intelligence analyst. Write a concise intelligence report "
        "for the following event(s). Use continuous prose — no bullet points. "
        "Use probability language (likely, assessed with moderate confidence, etc.).\n\n"
        f"{proximity_str}\n\n"
        "Events:\n"
        f"{digest}\n\n"
        "Respond ONLY with valid JSON matching this schema exactly:\n"
        '{"situation": "<2-4 sentences>", "impact": "<2-4 sentences>", "action": "<1-3 sentences>"}'
    )

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        return {
            "situation": data.get("situation", ""),
            "impact": data.get("impact", ""),
            "action": data.get("action", ""),
        }
    except Exception as exc:
        logger.warning("generate_report_sections_error", error=str(exc))
        title = events[0].get("title", "Unknown event") if events else "Unknown event"
        return {
            "situation": f"Reporting on: {title}",
            "impact": "Impact assessment unavailable — API error.",
            "action": "Review source reporting for further details.",
        }
