import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # License
    PLATFORM_URL: str = os.getenv("PLATFORM_URL", "")
    PROJECT_KEY: str = os.getenv("PROJECT_KEY", "")
    API_KEY: str = os.getenv("API_KEY", "")

    # Ollama settings
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    OLLAMA_FALLBACK_MODEL: str = os.getenv("OLLAMA_FALLBACK_MODEL", "mistral")

    # Safety settings
    READ_ONLY_MODE: bool = os.getenv("READ_ONLY_MODE", "false").lower() == "true"
    MAX_RESULT_ROWS: int = int(os.getenv("MAX_RESULT_ROWS", "100"))
    SAMPLE_ROWS_FOR_CONTEXT: int = int(os.getenv("SAMPLE_ROWS_FOR_CONTEXT", "3"))
    BLOCKED_TABLES: List[str] = [
        t.strip() for t in os.getenv("BLOCKED_TABLES", "").split(",") if t.strip()
    ]

    # Database (auto-connect on startup)
    DB_TYPE: str = os.getenv("DB_TYPE", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "")
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # Agent server
    AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8000"))


settings = Settings()
