from __future__ import annotations

import json
import logging

from groq import Groq

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM call fails (network, parse, timeout)."""


def call_llm(client: Groq, prompt: str, model: str, temperature: float = 0) -> dict:
    """Call Groq with JSON mode. Returns parsed dict or raises LLMError."""
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        result = json.loads(completion.choices[0].message.content)
        if not result:
            raise LLMError("LLM returned empty JSON object")
        return result
    except LLMError:
        raise
    except Exception as e:
        logger.warning(f"LLM call failed ({model}): {e}")
        raise LLMError(f"LLM call failed: {e}") from e
