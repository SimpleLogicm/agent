"""
LLM Provider - Supports both Gemini (Google) and Groq.
User can pick either. Or use Groq as fallback if Gemini quota exhausted.
"""

import logging
from config import settings

logger = logging.getLogger("agent")

_gemini_client = None
_groq_client = None


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            from google.genai import types as genai_types
            _gemini_client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=genai_types.HttpOptions(api_version="v1"),
            )
        except ImportError:
            raise Exception("google-genai not installed. Run: pip install google-genai")
    return _gemini_client


def _get_groq():
    global _groq_client
    if _groq_client is None:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=settings.GROQ_API_KEY)
        except ImportError:
            raise Exception("groq not installed. Run: pip install groq")
    return _groq_client


def _chat_gemini(prompt: str, temperature: float) -> str:
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


def _chat_groq(prompt: str, temperature: float) -> str:
    client = _get_groq()
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()


def chat(prompt: str, temperature: float = 0.1) -> str:
    """
    Try primary LLM first. Auto-fallback to the other if it fails.
    Priority: User's preferred provider → The other one as fallback.
    """
    provider = (settings.LLM_PROVIDER or "").lower()
    has_gemini = bool(settings.GEMINI_API_KEY)
    has_groq = bool(settings.GROQ_API_KEY)

    # Determine order of providers to try
    if provider == "groq" and has_groq:
        providers = ["groq"] + (["gemini"] if has_gemini else [])
    elif has_gemini:
        providers = ["gemini"] + (["groq"] if has_groq else [])
    elif has_groq:
        providers = ["groq"]
    else:
        raise Exception(
            "No AI provider configured. Set GEMINI_API_KEY (https://aistudio.google.com/apikey) "
            "or GROQ_API_KEY (https://console.groq.com/keys) in your .env file."
        )

    last_error = None
    for p in providers:
        try:
            if p == "gemini":
                return _chat_gemini(prompt, temperature)
            elif p == "groq":
                return _chat_groq(prompt, temperature)
        except Exception as e:
            err_str = str(e)
            logger.warning(f"  {p} failed: {err_str[:120]}")
            last_error = e
            # If it's a quota error, try next provider
            if "429" in err_str or "quota" in err_str.lower() or "exhausted" in err_str.lower():
                continue
            # For other errors also try fallback
            continue

    # All providers failed
    logger.error(f"All LLM providers failed. Last error: {last_error}")
    raise last_error if last_error else Exception("No AI provider available")
