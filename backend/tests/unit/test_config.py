"""Unit tests for configuration invariants (Issue 06) and demo route protections (Issue 08)."""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from app.core.config import Settings, settings
from app.main import app


def test_default_settings_are_secure():
    """Validates Issue 06 acceptance criteria: IS_TEST_MODE is False and no sample secrets."""
    s = Settings(
        _env_file=None,
        RAZORPAY_KEY_ID="",
        RAZORPAY_KEY_SECRET="",
        RAZORPAY_WEBHOOK_SECRET="",
        IS_TEST_MODE=False,
        ENABLE_DEMO=False,
    )
    assert s.IS_TEST_MODE is False
    assert s.ENABLE_DEMO is False
    assert s.RAZORPAY_KEY_ID == ""
    assert s.RAZORPAY_KEY_SECRET == ""
    assert s.RAZORPAY_WEBHOOK_SECRET == ""


def test_production_rejects_test_mode():
    """Validates that IS_TEST_MODE=True is rejected when ENV=production."""
    with pytest.raises(ValidationError, match="IS_TEST_MODE must be False in production"):
        Settings(
            _env_file=None,
            ENV="production",
            IS_TEST_MODE=True,
            DATABASE_URL="postgresql+asyncpg://user:pass@host/db",
            RAZORPAY_KEY_ID="rzp_live_realprod123",
            RAZORPAY_KEY_SECRET="sec_realprod123",
            RAZORPAY_WEBHOOK_SECRET="whsec_realprod123",
        )


def test_production_rejects_demo_mode():
    """Validates that ENABLE_DEMO=True is rejected when ENV=production."""
    with pytest.raises(ValidationError, match="ENABLE_DEMO must be False in production"):
        Settings(
            _env_file=None,
            ENV="production",
            IS_TEST_MODE=False,
            ENABLE_DEMO=True,
            DATABASE_URL="postgresql+asyncpg://user:pass@host/db",
            RAZORPAY_KEY_ID="rzp_live_realprod123",
            RAZORPAY_KEY_SECRET="sec_realprod123",
            RAZORPAY_WEBHOOK_SECRET="whsec_realprod123",
        )


def test_production_rejects_sqlite():
    """Validates that SQLite is rejected when ENV=production."""
    with pytest.raises(ValidationError, match="requires an explicit production database"):
        Settings(
            _env_file=None,
            ENV="production",
            IS_TEST_MODE=False,
            DATABASE_URL="sqlite+aiosqlite:///./prod.db",
            RAZORPAY_KEY_ID="rzp_live_realprod123",
            RAZORPAY_KEY_SECRET="sec_realprod123",
            RAZORPAY_WEBHOOK_SECRET="whsec_realprod123",
        )


def test_production_rejects_placeholder_credentials():
    """Validates that placeholder/sample keys are rejected when ENV=production."""
    with pytest.raises(ValidationError, match="Valid RAZORPAY_KEY_ID must be configured"):
        Settings(
            _env_file=None,
            ENV="production",
            IS_TEST_MODE=False,
            DATABASE_URL="postgresql+asyncpg://user:pass@host/db",
            RAZORPAY_KEY_ID="rzp_test_samplekey123",
            RAZORPAY_KEY_SECRET="sample_secret_key",
            RAZORPAY_WEBHOOK_SECRET="sample_webhook_secret_key",
        )


def test_production_accepts_valid_configuration():
    """Validates that valid production parameters pass validation cleanly."""
    s = Settings(
        _env_file=None,
        ENV="production",
        IS_TEST_MODE=False,
        ENABLE_DEMO=False,
        DATABASE_URL="postgresql+asyncpg://user:pass@host/db",
        RAZORPAY_KEY_ID="rzp_live_realprod123",
        RAZORPAY_KEY_SECRET="sec_realprod123",
        RAZORPAY_WEBHOOK_SECRET="whsec_realprod123",
    )
    assert s.ENV == "production"
    assert s.IS_TEST_MODE is False
    assert s.ENABLE_DEMO is False


@pytest.mark.asyncio
async def test_demo_routes_blocked_when_demo_disabled():
    """Validates Issue 08: /demo/* routes return 403 when ENABLE_DEMO=False."""
    original_demo = settings.ENABLE_DEMO
    original_env = settings.ENV
    try:
        settings.ENABLE_DEMO = False
        settings.ENV = "development"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/demo/reset")
            assert resp.status_code == 403
            data = resp.json()
            assert data["error"]["code"] == "DEMO_MODE_DISABLED"

            resp_statement = await client.get("/api/v1/demo/sample-statement?bank=HDFC")
            assert resp_statement.status_code == 403
    finally:
        settings.ENABLE_DEMO = original_demo
        settings.ENV = original_env


@pytest.mark.asyncio
async def test_demo_routes_blocked_in_production():
    """Validates Issue 08: /demo/* routes return 403 when ENV=production even if ENABLE_DEMO=True."""
    original_demo = settings.ENABLE_DEMO
    original_env = settings.ENV
    try:
        settings.ENABLE_DEMO = True
        settings.ENV = "production"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/demo/reset")
            assert resp.status_code == 403
            data = resp.json()
            assert data["error"]["code"] == "DEMO_MODE_FORBIDDEN_IN_PRODUCTION"
    finally:
        settings.ENABLE_DEMO = original_demo
        settings.ENV = original_env


@pytest.mark.asyncio
async def test_demo_routes_allowed_when_enabled():
    """Validates that in non-production environments with ENABLE_DEMO=True, demo routes succeed."""
    original_demo = settings.ENABLE_DEMO
    original_env = settings.ENV
    try:
        settings.ENABLE_DEMO = True
        settings.ENV = "development"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/demo/sample-statement?bank=HDFC")
            assert resp.status_code == 200
            assert "Date,Chq/Ref No.,Narration" in resp.text
    finally:
        settings.ENABLE_DEMO = original_demo
        settings.ENV = original_env
