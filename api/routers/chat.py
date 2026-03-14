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

    prompt = f"""You are a senior crisis communications analyst for a Global Security Operations Center (GSOC) at a major technology company with global operations. You support employee safety and business continuity across corporate offices, data centers, R&D labs, and supply chain partners worldwide.

An analyst has requested an on-demand intelligence briefing. Using ONLY the search results below, write a detailed leadership intelligence report. Your audience is VP-level security leadership who need to make operational decisions.

WRITING STANDARDS:
- Use probability language: "likely", "assessed", "appears", "may indicate", "is believed to"
- Never state uncertainties as confirmed facts
- Do NOT include numerical severity scores in prose
- Connect events to potential second/third-order effects on tech company operations (offices, data centers, supply chain, employee travel, cloud infrastructure)
- Include regional context: escalation patterns, historical precedent, or geopolitical dynamics
- CRITICAL: Each section MUST meet the minimum sentence count — do NOT write single-sentence responses

ANALYST QUERY: {query}
TODAY: {today_str}

SEARCH RESULTS:
{results_text}

Respond with JSON only. IMPORTANT — follow the sentence counts exactly:
{{"title": "brief headline max 10 words", "tier": "FLASH or PRIORITY or ROUTINE", "situation": "MUST be 3-5 sentences. First sentence: On {today_str}, [what happened, where, when, scale — confirmed facts only]. Following sentences: provide regional context — what led to this event, escalation trajectory, prior incidents, political/military dynamics. Include confirmed casualties, infrastructure damage, government responses, and strategic significance.", "impact": "MUST be 2-3 sentences. Analyze direct and cascading effects on tech company operations. Assess threats to employee safety, office/data center accessibility, business travel risk, cloud and infrastructure dependencies, semiconductor and hardware supply chain exposure, and potential for protest or civil unrest near corporate campuses. Use probability language.", "action": "MUST be 2-3 sentences. Specific executable GSOC actions with clear ownership. Examples: initiate employee accountability at [site], activate enhanced perimeter security, issue travel hold for [region], brief executive protection, coordinate with local LE liaison, pre-position crisis comms holding statement, escalate to CMT if [trigger]."}}"""

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
        "distro": "",
        "generated_at": now.isoformat(),
        "sources": [r.get("source", "") for r in search_results if r.get("source")],
        "query": query,
        "on_demand": True,
    }
