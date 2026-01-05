"""
BioLinker Configuration.

Load settings from environment variables with sensible defaults.
"""

import os
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # App
    APP_NAME: str = "BioLinker"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "sqlite:///./biolinker.db"
    
    # For PostgreSQL, use:
    # DATABASE_URL: str = "postgresql://user:password@localhost:5432/biolinker"
    
    # Authentication
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Redis (for Celery and caching)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # LLM Configuration
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "ministral-3:3b"
    LLM_BASE_URL: Optional[str] = "http://localhost:11434"
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # PubMed
    NCBI_API_KEY: Optional[str] = None
    NCBI_EMAIL: Optional[str] = None
    
    # Rate Limits (per user per month)
    FREE_TIER_SEARCHES: int = 100
    FREE_TIER_ARTICLES: int = 500
    PRO_TIER_SEARCHES: int = 1000
    PRO_TIER_ARTICLES: int = 5000
    
    # Feature Flags
    ENABLE_WAITLIST: bool = True
    REQUIRE_EMAIL_VERIFICATION: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()

