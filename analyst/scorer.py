"""
Gemini-powered noise filter + severity scorer.

Two separate API calls to preserve quota:
  1. is_noise()       — YES/NO single call
  2. score_severity() — int 1-10 via structured JSON response

Reads GEMINI_API_KEY from environment / config/.env.
"""

import json
import os
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

from collector.sources.base import RawArticle
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


def is_noise(article: RawArticle) -> bool:
    """
    Return True if Gemini classifies the article as noise.

    A noise article is irrelevant to a GSOC analyst: sports, entertainment,
    celebrity gossip, general business news with no security implications.
    """
    model = _get_model()
    prompt = (
        "You are a GSOC analyst triage assistant. "
        "Decide if the following article is NOISE (irrelevant to physical security, "
        "geopolitical risk, civil unrest, natural disaster, or executive travel safety). "
        "Reply with exactly one word: YES (noise) or NO (relevant).\n\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary[:300]}"
    )
    try:
        response = model.generate_content(prompt)
        answer = response.text.strip().upper()
        return answer.startswith("YES")
    except Exception as exc:
        logger.warning("is_noise_api_error", error=str(exc), article_id=article.article_id)
        return False  # Default: treat as relevant on API failure


def score_severity(article: RawArticle) -> int:
    """
    Return a severity score 1–10 for the article.

    10 = catastrophic immediate threat; 1 = minimal relevance.
    Returns 5 (mid-range) on API failure.
    """
    model = _get_model()
    prompt = (
        "You are a GSOC analyst. Score the severity of the following intelligence item "
        "on a scale of 1-10 for a multinational corporation with offices in major global cities.\n"
        "10 = catastrophic immediate threat (active attack, mass casualty, major natural disaster).\n"
        "1  = minimal relevance (distant, low-impact, speculative).\n\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary[:500]}\n\n"
        'Respond ONLY with valid JSON: {"severity": <integer 1-10>}'
    )
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Strip possible markdown fences
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        score = int(data.get("severity", 5))
        return max(1, min(10, score))
    except Exception as exc:
        logger.warning("score_severity_api_error", error=str(exc), article_id=article.article_id)
        return 5
