from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import require_roles
from customer_service_app.core.exceptions import PermissionDeniedError
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.infrastructure.db.repositories import OrderRepository
from customer_service_app.infrastructure.db.session import get_db_session


router = APIRouter(prefix="/orders", tags=["orders"])


class OrderSummaryView(BaseModel):
    order_id: str
    status: str
    product: str | None = None
    amount: float | None = None
    logistics_company: str | None = None
    tracking_number: str | None = None
    destination: str | None = None


@router.get("", response_model=list[OrderSummaryView])
async def list_my_orders(
    tenant_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> list[OrderSummaryView]:
    """列出当前登录用户名下的订单。

    这是 C 端"帮助与订单"入口的数据来源：用户先看到自己的订单，再针对某一单发起咨询。
    订单归属来自令牌主体，不接受前端传入的 user_id。
    """

    tenant_id, _ = authorize_identity(principal, tenant_id=tenant_id)
    user_id = principal.subject
    if not user_id:
        raise PermissionDeniedError("需要登录后才能查看订单")

    orders = await OrderRepository(session).list_for_user(
        tenant_id=tenant_id,
        user_id=user_id,
        limit=limit,
    )
    return [
        OrderSummaryView(
            order_id=order.order_id,
            status=order.status,
            product=(order.metadata_json or {}).get("product"),
            amount=(order.metadata_json or {}).get("amount"),
            logistics_company=order.logistics_company,
            tracking_number=order.tracking_number,
            destination=(order.metadata_json or {}).get("delivery_address"),
        )
        for order in orders
    ]
