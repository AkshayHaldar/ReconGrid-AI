"""Application configuration using Pydantic Settings."""

import base64
import binascii
from decimal import Decimal
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.secret_format import sealed_blob


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Razorpay Test / Live Configuration (No hardcoded sample secrets)
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # Urlsafe base64 of 32 random bytes. Secrets stored as "enc:..." are decrypted with it at use time.
    ENCRYPTION_MASTER_KEY: str = ""
    # HMAC key used to sign Audit Compliance Certificates. Empty means certificates carry a content hash only.
    AUDIT_SIGNING_KEY: str = ""

    # Database: Defaults to SQLite for zero-friction local run/tests, easily points to PostgreSQL
    DATABASE_URL: str = "sqlite+aiosqlite:///./recongrid.db"

    # Job Queue / Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # App Config
    ENV: Literal["development", "production", "testing"] = "development"
    DEBUG_ERRORS: bool = False
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    MAX_CSV_UPLOAD_MB: int = 10
    MAX_CSV_ROWS: int = 50000
    RECONCILIATION_TOLERANCE_INR: Decimal = Decimal("1.00")
    FUZZY_MATCH_CONFIDENCE_THRESHOLD: float = 0.90
    RAZORPAY_FETCH_MAX_RETRIES: int = 5
    GST_RATE: Decimal = Decimal("0.18")
    DEFAULT_MDR_RATE: Decimal = Decimal("0.02")
    TDS_194O_RATE: Decimal = Decimal("0.01")
    SETTLEMENT_PENDING_WINDOW_DAYS: int = 5

    # Settlement Q&A Agent & OCR
    LLM_PROVIDER: str = "nvidia"  # "nvidia", "openai", "anthropic", "ollama", or "vllm"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "meta/llama-3.1-70b-instruct"
    LLM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    # OCR / Vision Configuration (Optional for scanned PDFs)
    OCR_API_KEY: str = ""
    OCR_PROVIDER: str = "gemini"  # "gemini", "openai", "ocr_space"
    OCR_GEMINI_MODEL: str = "gemini-1.5-flash"
    OCR_OPENAI_MODEL: str = "gpt-4o-mini"
    OCR_OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    GEMINI_API_KEY: str = ""

    # Feature Flags
    IS_TEST_MODE: bool = False
    ENABLE_DEMO: bool = False

    # Observability & Metrics Configuration
    METRICS_BEARER_TOKEN: str = ""
    METRICS_INTERNAL_IPS: list[str] = [
        "127.0.0.1",
        "::1",
        "localhost",
    ]

    @model_validator(mode="after")
    def validate_production_invariants(self) -> "Settings":
        """Enforces Issue 06 & Issue 08 acceptance criteria for production environments."""
        if self.ENV == "production":
            if self.IS_TEST_MODE:
                raise ValueError("IS_TEST_MODE must be False in production environments.")

            if self.ENABLE_DEMO:
                raise ValueError("ENABLE_DEMO must be False in production environments.")

            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError(
                    "Production environment requires an explicit production database (PostgreSQL), SQLite is not permitted."
                )

            # Reject empty or placeholder secrets in production
            invalid_placeholders = {
                "rzp_test_samplekey123",
                "sample_secret_key",
                "sample_webhook_secret_key",
                "rzp_test_your_key_id_here",
                "your_razorpay_key_secret_here",
                "your_webhook_secret_here",
            }

            if (
                not self.RAZORPAY_KEY_ID
                or self.RAZORPAY_KEY_ID in invalid_placeholders
                or "sample" in self.RAZORPAY_KEY_ID
            ):
                raise ValueError("Valid RAZORPAY_KEY_ID must be configured for production.")

            if not self.RAZORPAY_KEY_SECRET or self.RAZORPAY_KEY_SECRET in invalid_placeholders:
                raise ValueError("Valid RAZORPAY_KEY_SECRET must be configured for production.")

            if not self.RAZORPAY_WEBHOOK_SECRET or self.RAZORPAY_WEBHOOK_SECRET in invalid_placeholders:
                raise ValueError("Valid RAZORPAY_WEBHOOK_SECRET must be configured for production.")

        self._validate_encryption_key()
        return self

    def _validate_encryption_key(self) -> None:
        """Fail at startup, not on the first Razorpay call, if encrypted secrets have no usable key."""
        if not any(
            sealed_blob(secret) is not None for secret in (self.RAZORPAY_KEY_SECRET, self.RAZORPAY_WEBHOOK_SECRET)
        ):
            return
        try:
            key = base64.urlsafe_b64decode(self.ENCRYPTION_MASTER_KEY.encode("ascii"))
        except (binascii.Error, UnicodeEncodeError):
            key = b""
        if len(key) != 32:
            raise ValueError(
                "ENCRYPTION_MASTER_KEY must be set to urlsafe base64 of 32 bytes when any secret is stored as 'enc:...'."
            )


settings = Settings()
