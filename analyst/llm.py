from __future__ import annotations

import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# ── Rate limiter: 15 requests per minute (1 request every 4 seconds) ──
_RPM_LIMIT = 15
_MIN_INTERVAL = 60.0 / _RPM_LIMIT
_last_call_time: float = 0.0
_rate_lock = threading.Lock()

# ── Provider state ──
_groq_client = None
_gemini_configured = False


def _wait_for_rate_limit() -> None:
    """Block until enough time has passed since the last LLM call."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        if elapsed < _MIN_INTERVAL:
            wait = _MIN_INTERVAL - elapsed
            logger.debug(f"Rate limiter: waiting {wait:.1f}s")
            time.sleep(wait)
        _last_call_time = time.monotonic()


class LLMError(Exception):
    """Raised when the LLM call fails (network, parse, timeout)."""


def configure_llm(api_key: str) -> None:
    """Configure LLM providers. api_key is kept for backward compat but keys come from env."""
    global _groq_client, _gemini_configured

    groq_key = os.getenv("GROQ_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")

    if groq_key:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=groq_key)
            logger.info("LLM: Groq configured (primary)")
        except Exception as e:
            logger.warning(f"LLM: Failed to configure Groq: {e}")

    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            _gemini_configured = True
            logger.info("LLM: Gemini configured (fallback)")
        except Exception as e:
            logger.warning(f"LLM: Failed to configure Gemini: {e}")

    if not _groq_client and not _gemini_configured:
        raise LLMError("No LLM provider configured — set GROQ_API_KEY or GEMINI_API_KEY")


# ── Provider mapping: model_name -> groq model ──
_GROQ_MODEL = "llama-3.3-70b-versatile"
_GEMINI_MODEL = "gemini-2.5-flash"


def _call_groq(prompt: str, temperature: float) -> dict:
    """Call Groq and return parsed JSON dict."""
    response = _groq_client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content
    result = json.loads(text)
    if not result:
        raise LLMError("Groq returned empty JSON object")
    return result


def _call_gemini(prompt: str, temperature: float) -> dict:
    """Call Gemini and return parsed JSON dict."""
    import google.generativeai as genai
    model = genai.GenerativeModel(_GEMINI_MODEL)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=temperature,
        ),
    )
    result = json.loads(response.text)
    if not result:
        raise LLMError("Gemini returned empty JSON object")
    return result


def _is_rate_limit(error: Exception) -> bool:
    """Check if the error is a rate limit (429) error."""
    error_str = str(error).lower()
    return "429" in error_str or "rate_limit" in error_str or "rate limit" in error_str


def call_llm(model_name: str, prompt: str, temperature: float = 0) -> dict:
    """Call LLM with automatic fallback. Tries Groq first, falls back to Gemini on rate limit."""
    _wait_for_rate_limit()

    # Build provider chain: primary first, fallback second
    providers = []
    if _groq_client:
        providers.append(("Groq", _call_groq))
    if _gemini_configured:
        providers.append(("Gemini", _call_gemini))

    if not providers:
        raise LLMError("No LLM provider configured")

    last_error = None
    for provider_name, call_fn in providers:
        try:
            result = call_fn(prompt, temperature)
            return result
        except Exception as e:
            last_error = e
            if _is_rate_limit(e) and len(providers) > 1:
                logger.warning(f"{provider_name} rate limited — falling back to next provider")
                continue
            elif len(providers) > 1:
                logger.warning(f"{provider_name} failed ({e}) — falling back to next provider")
                continue
            else:
                break

    logger.warning(f"All LLM providers failed. Last error: {last_error}")
    raise LLMError(f"All LLM providers failed: {last_error}") from last_error
