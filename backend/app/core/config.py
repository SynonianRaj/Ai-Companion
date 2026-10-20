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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
