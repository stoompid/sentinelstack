from __future__ import annotations

import json
import logging

from groq import Groq

logger = logging.getLogger(__name__)


def call_llm(client: Groq, prompt: str, model: str, temperature: float = 0) -> dict:
    """Call Groq with JSON mode. Returns parsed dict, or {} on any failure."""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        logger.warning(f"LLM call failed ({model}): {e}")
        return {}
