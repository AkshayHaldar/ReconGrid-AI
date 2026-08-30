"""Application configuration using Pydantic Settings."""

from decimal import Decimal
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Razorpay Test / Live Configuration
    RAZORPAY_KEY_ID: str = "rzp_test_samplekey123"
    RAZORPAY_KEY_SECRET: str = "sample_secret_key"
    RAZORPAY_WEBHOOK_SECRET: str = "sample_webhook_secret_key"

    # Database: Defaults to SQLite for zero-friction local run/tests, easily points to PostgreSQL
    DATABASE_URL: str = "sqlite+aiosqlite:///./recongrid.db"

    # Job Queue / Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # App Config
    ENV: Literal["development", "production", "testing"] = "development"
    MAX_CSV_UPLOAD_MB: int = 10
    MAX_CSV_ROWS: int = 50000
    RECONCILIATION_TOLERANCE_INR: Decimal = Decimal("1.00")
    FUZZY_MATCH_CONFIDENCE_THRESHOLD: float = 0.90
    RAZORPAY_FETCH_MAX_RETRIES: int = 5
    GST_RATE: Decimal = Decimal("0.18")

    # Settlement Q&A Agent & OCR
    LLM_PROVIDER: str = "nvidia"  # "nvidia", "openai", or "anthropic"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "meta/llama-3.3-70b-instruct"
    LLM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    # OCR / Vision Configuration (Optional for scanned PDFs)
    OCR_API_KEY: str = ""
    OCR_PROVIDER: str = "gemini"  # "gemini", "openai", "ocr_space"
    GEMINI_API_KEY: str = ""

    # Feature Flags
    IS_TEST_MODE: bool = True


settings = Settings()
