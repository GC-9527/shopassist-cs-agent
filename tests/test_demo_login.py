from __future__ import annotations

import pytest

from customer_service_app.api.routes_auth import DemoTokenRequest, issue_demo_token
from customer_service_app.core.config import Settings
from customer_service_app.core.exceptions import AppError
from customer_service_app.core.security import decode_access_token, principal_from_claims


def _settings(**overrides: object) -> Settings:
    base = {
        "jwt_secret_key": "test-secret-key",
        "jwt_issuer": "shopassist",
        "jwt_audience": "shopassist-console",
        "security_enabled": True,
        "demo_login_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_token_carries_identity_and_role() -> None:
    settings = _settings()

    issued = await issue_demo_token(DemoTokenRequest(user_id="u001"), settings)
    principal = principal_from_claims(decode_access_token(issued.access_token, settings))

    assert principal.subject == "u001"
    assert principal.tenant_id == "default"
    assert "customer" in principal.roles
    assert issued.roles == ["customer"]


@pytest.mark.asyncio
async def test_agent_account_gets_agent_role() -> None:
    settings = _settings()

    issued = await issue_demo_token(DemoTokenRequest(user_id="u003"), settings)

    assert issued.roles == ["agent"]


@pytest.mark.asyncio
async def test_unknown_account_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        await issue_demo_token(DemoTokenRequest(user_id="u999"), _settings())

    assert excinfo.value.code == "demo_account_not_allowed"


@pytest.mark.asyncio
async def test_disabled_when_security_is_off() -> None:
    with pytest.raises(AppError) as excinfo:
        await issue_demo_token(
            DemoTokenRequest(user_id="u001"), _settings(security_enabled=False)
        )

    assert excinfo.value.code == "security_disabled"


@pytest.mark.asyncio
async def test_disabled_when_demo_login_is_off() -> None:
    with pytest.raises(AppError) as excinfo:
        await issue_demo_token(
            DemoTokenRequest(user_id="u001"), _settings(demo_login_enabled=False)
        )

    assert excinfo.value.code == "demo_login_disabled"
