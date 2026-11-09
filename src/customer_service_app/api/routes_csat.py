from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import require_roles
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.domain.csat import CsatSummaryView
from customer_service_app.infrastructure.db.session import get_db_session
from customer_service_app.services.csat_service import CsatService


router = APIRouter(prefix="/csat", tags=["csat"])


@router.get("/summary", response_model=CsatSummaryView)
async def csat_summary(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(require_roles("agent", "operator", "admin")),
) -> CsatSummaryView:
    """后台满意度看板：均分、好评率、分布与最近评价。

    只给坐席/运营/管理员看；客户提交评价走
    `POST /conversations/{id}/csat`，不能读全租户的汇总。
    """

    tenant_id, _ = authorize_identity(principal, tenant_id=tenant_id)
    return await CsatService(session).summary(tenant_id=tenant_id, days=days)
