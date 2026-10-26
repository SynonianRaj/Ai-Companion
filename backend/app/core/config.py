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
    LLM_PROVIDER: str = "gemini"  # "gemini", "groq", "mock", "openai"
    LLM_TEMPERATURE: float = 0.8
    GROQ_API_KEY: Union[str, None] = None
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_FALLBACK_MODEL: str = "openai/gpt-oss-20b"
    GROQ_MAX_TOKENS: int = 600
    GROQ_FALLBACK_MAX_TOKENS: int = 800
    GEMINI_API_KEY: Union[str, None] = None
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_MAX_TOKENS: int = 600
    GEMINI_THINKING_BUDGET: int = 0
    OPENAI_API_KEY: Union[str, None] = None
    OPENAI_API_BASE: Union[str, None] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    RENDER_EXTERNAL_URL: Union[str, None] = None

    # Availability & Timing Constants (seconds)
    REPLY_DELAY_QUICK_MIN: float = 2.0
    REPLY_DELAY_QUICK_MAX: float = 8.0
    REPLY_DELAY_MODERATE_MIN: float = 15.0
    REPLY_DELAY_MODERATE_MAX: float = 45.0
    REPLY_DELAY_BUSY_MIN: float = 120.0       # 2 min
    REPLY_DELAY_BUSY_MAX: float = 1800.0      # 30 min
    REPLY_DELAY_SLEEPING_MIN: float = 600.0    # 10 min
    REPLY_DELAY_SLEEPING_MAX: float = 14400.0  # 4 hours

    # Long gap chance when free (5-10% chance)
    FREE_LONG_GAP_CHANCE: float = 0.08
    FREE_LONG_GAP_MIN: float = 600.0          # 10 min
    FREE_LONG_GAP_MAX: float = 2400.0         # 40 min

    # Seen delay ranges (seconds before chat is opened)
    SEEN_DELAY_FREE_MIN: float = 1.5
    SEEN_DELAY_FREE_MAX: float = 5.0
    SEEN_DELAY_BUSY_MIN: float = 30.0
    SEEN_DELAY_BUSY_MAX: float = 300.0        # 5 min
    SEEN_DELAY_SLEEPING_MIN: float = 1800.0   # 30 min

    # Propensity hints for prompt only (LLM still decides)
    PROPENSITY_HINTS: dict = {
        "free": {"reply_now": 85, "reply_later": 15, "ignore_until_free": 0},
        "working": {"reply_now": 40, "reply_later": 45, "ignore_until_free": 15},
        "sleeping": {"reply_now": 10, "reply_later": 25, "ignore_until_free": 65},
        "winding_down": {"reply_now": 60, "reply_later": 30, "ignore_until_free": 10}
    }

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
