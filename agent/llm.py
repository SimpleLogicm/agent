"""
LLM Provider - Google Gemini (free, fast, 1M context).
Only question + schema is sent to Gemini. Data results also go for answer generation.
"""

import logging
from config import settings

logger = logging.getLogger("agent")

_gemini_model = None


def _get_gemini():
    global _gemini_model
    if _gemini_model is None:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            _gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)
        except ImportError:
            raise Exception("google-generativeai not installed. Run: pip install google-generativeai")
    return _gemini_model


def chat(prompt: str, temperature: float = 0.1) -> str:
    """Send a prompt to Gemini and return the response text."""
    if not settings.GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey")

    try:
        import google.generativeai as genai
        model = _get_gemini()
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=2000,
            ),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        raise
