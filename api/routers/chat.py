"""On-demand intelligence chatbot — web search + Groq report generation."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str


def _search_web(query: str, max_results: int = 8) -> list[dict]:
    """Search the web for news using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
        return results
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


def _generate_report(query: str, search_results: list[dict]) -> dict:
    """Feed search results to Groq and generate a GSOC-formatted report."""
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    client = Groq(api_key=api_key)

    results_text = "\n\n".join(
        f"Title: {r.get('title', 'N/A')}\n"
        f"Source: {r.get('source', 'N/A')}\n"
        f"Date: {r.get('date', 'N/A')}\n"
        f"Body: {r.get('body', r.get('description', 'N/A'))[:300]}"
        for r in search_results
    )

    now = datetime.now(tz=timezone.utc)
    today_str = now.strftime(f"%A, %B {now.day}, %Y")

    prompt = f"""You are a crisis communications writer for a Global Security Operations Center (GSOC).
An analyst has requested an on-demand intelligence briefing. Using ONLY the search results below, write a concise leadership intelligence report.

Use probability language where appropriate: "likely", "assessed", "appears", "may indicate".
Never state uncertainties as confirmed facts. Do NOT include numerical severity scores in prose.

ANALYST QUERY: {query}
TODAY: {today_str}

SEARCH RESULTS:
{results_text}

DISTRIBUTION MATRIX — select the best match:
- Active Assailant: "ACTIVE ASSAILANT - T[tier] (Region - Type)"
- Bomb/Explosion: "BOMB THREAT - T[tier] (Region - Type)"
- LE Activity Off-Site: "LE ACTIVITY - T[tier] (Region - Type)"
- Civil Unrest/Protest: "CIVIL UNREST - T[tier] (Region - Type)"
- Natural Disaster/Weather: "NATURAL DISASTER - T[tier] (Region - Type)"
- Geopolitical/Conflict: "GEOPOLITICAL - T[tier] (Region - Type)"
- General/Other: "GENERAL SAFETY - T[tier] (Region - Type)"
- Low-impact awareness: "FYSA - T1 (AMER/EMEA)"

Respond with JSON only:
{{"title": "brief headline max 10 words", "tier": "FLASH or PRIORITY or ROUTINE", "situation": "On {today_str}, [what happened, where, when, scale — confirmed facts only].", "impact": "Direct physical and operational effects on employee safety, office accessibility, travel. Use probability language. Omit if no direct company impact.", "action": "1-2 sentences. Specific executable GSOC actions.", "distro": "recommended distribution list from the matrix above"}}"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return json.loads(completion.choices[0].message.content)


@router.post("/chat")
def chat_intel(req: ChatRequest):
    """Search the web and generate an on-demand GSOC intelligence report."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    search_results = _search_web(query)
    if not search_results:
        raise HTTPException(
            status_code=404,
            detail="No search results found. Try a different query.",
        )

    try:
        report = _generate_report(query, search_results)
    except Exception as e:
        logger.error(f"Chat report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")

    now = datetime.now(tz=timezone.utc)

    return {
        "report_id": str(uuid.uuid4()),
        "title": report.get("title", "Intelligence Briefing"),
        "tier": report.get("tier", "ROUTINE"),
        "situation": report.get("situation", ""),
        "impact": report.get("impact", ""),
        "action": report.get("action", ""),
        "distro": report.get("distro", ""),
        "generated_at": now.isoformat(),
        "sources": [r.get("source", "") for r in search_results if r.get("source")],
        "query": query,
        "on_demand": True,
    }
