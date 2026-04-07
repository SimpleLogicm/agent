"""
LLM Provider - supports both Groq (fast, cloud) and Ollama (slow, local).
Only sends questions + table names to cloud. Actual data NEVER leaves.
"""

import os
import json
import logging
from typing import Optional
from config import settings

logger = logging.getLogger("agent")

# Groq client (lazy loaded)
_groq_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=settings.GROQ_API_KEY)
        except ImportError:
            raise Exception("groq package not installed. Run: pip install groq")
    return _groq_client


def chat(prompt: str, temperature: float = 0.1) -> str:
    """Send a prompt to LLM and return the response text."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "groq" and settings.GROQ_API_KEY:
        return _chat_groq(prompt, temperature)
    else:
        return _chat_ollama(prompt, temperature)


def _chat_groq(prompt: str, temperature: float) -> str:
    """Fast cloud LLM via Groq (free tier)."""
    try:
        client = _get_groq()
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=1500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Groq failed: {e}. Falling back to Ollama.")
        return _chat_ollama(prompt, temperature)


def _chat_ollama(prompt: str, temperature: float) -> str:
    """Local LLM via Ollama."""
    import ollama
    response = ollama.chat(
        model=settings.OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": temperature},
    )
    return response["message"]["content"].strip()
