"""
LLM Provider - Google Gemini (free, fast, 1M context).
Uses the new google-genai SDK which supports v1 API.
"""

import logging
from config import settings

logger = logging.getLogger("agent")

_gemini_client = None


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        except ImportError:
            raise Exception("google-genai not installed. Run: pip install google-genai")
    return _gemini_client


def chat(prompt: str, temperature: float = 0.1) -> str:
    """Send a prompt to Gemini and return the response text."""
    if not settings.GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey")

    try:
        from google.genai import types
        client = _get_gemini()
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=2000,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        raise
