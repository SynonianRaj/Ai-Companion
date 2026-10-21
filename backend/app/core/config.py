from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import json


class Settings(BaseSettings):
    APP_NAME: str = "AI Companion"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "local-dev-prototype-secret-key-2026-safe"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./ai_companion_dev.db"
    
    # Helplines (Verified Government of India Helplines)
    TELE_MANAS_HELPLINE: str = "14416 / 1800-891-4416"
    KIRAN_HELPLINE: str = "1800-599-0019"
    EMERGENCY_HELPLINE: str = "112"
    
    # Lifecycle constants
    INACTIVITY_EXPIRY_DAYS: int = 15
    INACTIVITY_REMINDER_DAYS: int = 12

    # LLM Settings (Option 3: Hybrid Architecture)
    LLM_PROVIDER: str = "mock"  # "mock", "groq", "gemini", "openai"
    GROQ_API_KEY: Union[str, None] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_FALLBACK_MODEL: str = "openai/gpt-oss-20b"
    GEMINI_API_KEY: Union[str, None] = None
    GEMINI_MODEL: str = "gemini-1.5-flash"
    OPENAI_API_KEY: Union[str, None] = None
    OPENAI_API_BASE: Union[str, None] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Rate Limiting (survives dyno spin-downs via DB)
    RATE_LIMIT_PER_MINUTE: int = 6
    RATE_LIMIT_PER_DAY: int = 40

    # Cron & Background Scheduler
    CRON_SECRET: str = "pilot-cron-secret-2026"
    TICK_BATCH_SIZE: int = 5
    TRIAL_DURATION_DAYS: int = 14

    # Web Push (VAPID)
    VAPID_PUBLIC_KEY: Union[str, None] = None
    VAPID_PRIVATE_KEY: Union[str, None] = None
    VAPID_CLAIM_EMAIL: str = "admin@ai-companion.local"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
