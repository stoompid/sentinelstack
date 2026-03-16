"""On-demand intelligence chatbot — web search + LLM report generation."""

from __future__ import annotations

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
    """Feed search results to LLM and generate a GSOC-formatted report."""
    from analyst.llm import call_llm, configure_llm

    # Ensure LLM is configured (idempotent)
    configure_llm("")

    results_text = "\n\n".join(
        f"Title: {r.get('title', 'N/A')}\n"
        f"Source: {r.get('source', 'N/A')}\n"
        f"Date: {r.get('date', 'N/A')}\n"
        f"Body: {r.get('body', r.get('description', 'N/A'))[:300]}"
        for r in search_results
    )

    now = datetime.now(tz=timezone.utc)
    today_str = now.strftime(f"%A, %B {now.day}, %Y")

    prompt = f"""You are a senior crisis communications analyst for a Global Security Operations Center (GSOC) at a major technology company. You support employee safety across corporate offices, data centers, and R&D labs worldwide.

An analyst has requested an on-demand intelligence briefing. Using ONLY the search results below, write a leadership intelligence report. Your audience is VP-level security leadership who need to make decisions about employee safety and site security.

WRITING STANDARDS:
- Use probability language: "likely", "assessed", "appears", "may indicate"
- Never state uncertainties as confirmed facts
- Do NOT include numerical severity scores in prose
- Be concise and direct — no filler or repetition
- CRITICAL: Each section MUST meet the minimum sentence count

ANALYST QUERY: {query}
TODAY: {today_str}

SEARCH RESULTS:
{results_text}

Respond with JSON only. Follow the sentence counts exactly:
{{"title": "brief headline max 10 words", "tier": "FLASH or PRIORITY or ROUTINE", "situation": "MUST be 3-5 sentences. First sentence: On {today_str}, [what happened, where, scale — confirmed facts only]. Following sentences: regional context, escalation trajectory, prior incidents, confirmed casualties or infrastructure damage, government responses.", "impact": "MUST be 2-3 sentences. Focus ONLY on: (1) are employees in the affected area safe, (2) can they get to/from the office, (3) is travel to the region disrupted. Do NOT speculate about supply chains, semiconductors, or cloud infrastructure unless the event directly threatens them. Be specific about which offices or regions are affected.", "action": "MUST be 2-3 sentences. Specific executable GSOC actions: initiate employee accountability at [site], issue travel hold for [region], activate enhanced perimeter security, brief executive protection, coordinate with local LE, escalate to CMT if [trigger]."}}"""

    return call_llm("auto", prompt, temperature=0.3)


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
