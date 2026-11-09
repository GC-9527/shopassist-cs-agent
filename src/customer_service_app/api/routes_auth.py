from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from customer_service_app.core.config import Settings, get_settings
from customer_service_app.core.exceptions import AppError
from customer_service_app.core.security import create_access_token


router = APIRouter(prefix="/auth", tags=["auth"])


class DemoTokenRequest(BaseModel):
    """演示登录请求。生产环境应替换为企业 SSO 或身份服务。"""

    user_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(default="default", min_length=1, max_length=64)


class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: str
    user_id: str
    roles: list[str]


def demo_accounts(settings: Settings) -> dict[str, str]:
    """解析 `user_id:role` 形式的演示账号白名单。"""

    accounts: dict[str, str] = {}
    for item in settings.demo_login_users.split(","):
        piece = item.strip()
        if not piece:
            continue
        user_id, _, role = piece.partition(":")
        accounts[user_id.strip()] = (role or "customer").strip()
    return accounts


@router.post("/demo-token", response_model=DemoTokenResponse)
async def issue_demo_token(
    request: DemoTokenRequest,
    settings: Settings = Depends(get_settings),
) -> DemoTokenResponse:
    """给白名单内的演示账号签发短期令牌。

    这个端点不是认证系统：它只解决"本地演示怎么拿到可信凭证"。
    真正的身份来源应该是企业 SSO，签发的令牌只能代表白名单里的账号；
    开放给任意账号就等于没有认证，所以默认关闭。
    """

    if not settings.security_enabled:
        raise AppError(
            "鉴权未开启，演示登录不可用",
            code="security_disabled",
            status_code=403,
        )
    if not settings.demo_login_enabled:
        raise AppError(
            "演示登录未开启",
            code="demo_login_disabled",
            status_code=403,
        )

    accounts = demo_accounts(settings)
    role = accounts.get(request.user_id)
    if role is None:
        raise AppError(
            "该账号不在演示白名单内",
            code="demo_account_not_allowed",
            status_code=403,
        )

    token = create_access_token(
        request.user_id,
        settings,
        extra={"tenant_id": request.tenant_id, "roles": [role]},
    )
    return DemoTokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        roles=[role],
    )
