import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AgentTrace"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api"
    
    # Storage
    DATABASE_URL: str = os.getenv(
        "AGENTTRACE_DB_URL",
        "sqlite:////tmp/agenttrace.db" if os.getenv("VERCEL") else "sqlite:///./agenttrace.db"
    )
    
    # Replay Configuration
    DEFAULT_REPLAY_COUNT: int = 10
    CONFIDENCE_THRESHOLD: float = 0.70
    
    # Tool Side Effect Policy
    SIDE_EFFECT_KEYWORDS: List[str] = [
        "refund", "payment", "charge", "email", "sms", "send", "post", 
        "delete", "update", "create", "write", "mutate", "transfer", "cancel"
    ]
    
    # LLM Analyzer (Open Model / Ollama / OpenAI-compatible / Local heuristic fallback)
    LLM_PROVIDER: str = os.getenv("AGENTTRACE_LLM_PROVIDER", "heuristic")  # "ollama", "openai", "heuristic"
    LLM_MODEL: str = os.getenv("AGENTTRACE_LLM_MODEL", "qwen2.5:7b")
    LLM_API_BASE: str = os.getenv("AGENTTRACE_LLM_API_BASE", "http://localhost:11434/v1")
    LLM_API_KEY: Optional[str] = os.getenv("AGENTTRACE_LLM_API_KEY", None)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
