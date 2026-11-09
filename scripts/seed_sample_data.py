from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_service_app.infrastructure.db.models import Order  # noqa: E402
from customer_service_app.infrastructure.db.session import (  # noqa: E402
    dispose_engine,
    session_context,
)


def _order(
    *,
    tenant_id: str,
    user_id: str,
    order_id: str,
    status: str,
    product: str,
    amount: float,
    address: str,
    purchased_at: str,
    logistics_company: str | None = None,
    tracking_number: str | None = None,
    after_sale_days: int | None = None,
) -> dict:
    currency = "CNY" if tenant_id == "zh" else "USD"
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "order_id": order_id,
        "status": status,
        "logistics_company": logistics_company,
        "tracking_number": tracking_number,
        "metadata_json": {
            "amount": amount,
            "currency": currency,
            "product": product,
            "after_sale_days": after_sale_days or (7 if tenant_id == "zh" else 30),
            "delivery_address": address,
            "purchased_at": purchased_at,
        },
    }


ORDERS = [
    # ---- 中文站：三个客户，覆盖待发货 / 已发货 / 已签收 / 已退款 / 已取消 ----
    _order(
        tenant_id="zh",
        user_id="u001",
        order_id="202606040001",
        status="shipped",
        product="智能耳机",
        amount=299,
        address="上海市 静安区",
        purchased_at="2026-06-04",
        logistics_company="顺丰速运",
        tracking_number="SF1234567890",
    ),
    _order(
        tenant_id="zh",
        user_id="u001",
        order_id="202605280014",
        status="delivered",
        product="氮化镓充电器 65W",
        amount=129,
        address="上海市 静安区",
        purchased_at="2026-05-28",
        logistics_company="顺丰速运",
        tracking_number="SF1234567891",
    ),
    _order(
        tenant_id="zh",
        user_id="u001",
        order_id="202605150002",
        status="paid",
        product="磁吸充电宝 10000mAh",
        amount=199,
        address="上海市 静安区",
        purchased_at="2026-06-05",
    ),
    _order(
        tenant_id="zh",
        user_id="u001",
        order_id="202604200007",
        status="cancelled",
        product="USB-C 编织数据线",
        amount=39,
        address="上海市 静安区",
        purchased_at="2026-04-20",
    ),
    _order(
        tenant_id="zh",
        user_id="u002",
        order_id="202606030008",
        status="delivered",
        product="蓝牙音箱",
        amount=399,
        address="北京市 朝阳区",
        purchased_at="2026-06-03",
        logistics_company="京东物流",
        tracking_number="JDVA00012345678",
    ),
    _order(
        tenant_id="zh",
        user_id="u002",
        order_id="202605210011",
        status="shipped",
        product="车载充电器",
        amount=89,
        address="北京市 朝阳区",
        purchased_at="2026-05-21",
        logistics_company="中通快递",
        tracking_number="ZTO70001234567",
    ),
    _order(
        tenant_id="zh",
        user_id="u002",
        order_id="202604180005",
        status="refunded",
        product="桌面充电站",
        amount=259,
        address="北京市 朝阳区",
        purchased_at="2026-04-18",
    ),
    _order(
        tenant_id="zh",
        user_id="u005",
        order_id="202606010003",
        status="shipped",
        product="智能投影仪",
        amount=1299,
        address="深圳市 南山区",
        purchased_at="2026-06-01",
        logistics_company="顺丰速运",
        tracking_number="SF9988776655",
    ),
    _order(
        tenant_id="zh",
        user_id="u005",
        order_id="202605190009",
        status="delivered",
        product="磁吸无线充电器",
        amount=159,
        address="深圳市 南山区",
        purchased_at="2026-05-19",
        logistics_company="圆通速递",
        tracking_number="YT1234567890",
    ),
    _order(
        tenant_id="zh",
        user_id="u005",
        order_id="202605090006",
        status="paid",
        product="三口氮化镓充电器",
        amount=169,
        address="深圳市 南山区",
        purchased_at="2026-06-06",
    ),
    # ---- 英文站（中国品牌出海）：同样三个客户，美国站口径 ----
    _order(
        tenant_id="us",
        user_id="u001",
        order_id="ORD-2026-100234",
        status="shipped",
        product="Wireless Earbuds Pro",
        amount=79.99,
        address="Seattle, WA",
        purchased_at="2026-06-02",
        logistics_company="UPS",
        tracking_number="1Z999AA10123456784",
    ),
    _order(
        tenant_id="us",
        user_id="u001",
        order_id="ORD-2026-100198",
        status="delivered",
        product="65W GaN Charger",
        amount=45.99,
        address="Seattle, WA",
        purchased_at="2026-05-26",
        logistics_company="USPS",
        tracking_number="9400111899223856720001",
    ),
    _order(
        tenant_id="us",
        user_id="u001",
        order_id="ORD-2026-100155",
        status="paid",
        product="Magnetic Power Bank 10000mAh",
        amount=59.99,
        address="Seattle, WA",
        purchased_at="2026-06-05",
    ),
    _order(
        tenant_id="us",
        user_id="u002",
        order_id="ORD-2026-100301",
        status="delivered",
        product="Bluetooth Speaker",
        amount=89.99,
        address="Austin, TX",
        purchased_at="2026-06-01",
        logistics_company="UPS",
        tracking_number="1Z999AA10123456785",
    ),
    _order(
        tenant_id="us",
        user_id="u002",
        order_id="ORD-2026-100266",
        status="shipped",
        product="Car Charger",
        amount=24.99,
        address="Austin, TX",
        purchased_at="2026-05-20",
        logistics_company="FedEx",
        tracking_number="770123456789",
    ),
    _order(
        tenant_id="us",
        user_id="u002",
        order_id="ORD-2026-100120",
        status="refunded",
        product="USB-C Cable",
        amount=14.99,
        address="Austin, TX",
        purchased_at="2026-04-16",
    ),
    _order(
        tenant_id="us",
        user_id="u005",
        order_id="ORD-2026-100410",
        status="shipped",
        product="4K Projector",
        amount=229.99,
        address="San Jose, CA",
        purchased_at="2026-06-01",
        logistics_company="FedEx",
        tracking_number="770987654321",
    ),
    _order(
        tenant_id="us",
        user_id="u005",
        order_id="ORD-2026-100380",
        status="delivered",
        product="Magnetic Wireless Charger",
        amount=35.99,
        address="San Jose, CA",
        purchased_at="2026-05-18",
        logistics_company="UPS",
        tracking_number="1Z999AA10123456786",
    ),
    _order(
        tenant_id="us",
        user_id="u005",
        order_id="ORD-2026-100350",
        status="paid",
        product="3-Port GaN Charger",
        amount=39.99,
        address="San Jose, CA",
        purchased_at="2026-06-06",
    ),
]

LEGACY_ORDER_IDS = ("202606040001", "ORD-2026-100234")


async def seed() -> None:
    """写入两套演示订单：中文租户与英文租户，各覆盖三个客户。"""

    try:
        async with session_context() as session:
            # 清掉早期用 default 租户写入的同名单号，避免演示时出现重复口径。
            await session.execute(
                delete(Order).where(Order.tenant_id == "default").where(
                    Order.order_id.in_(LEGACY_ORDER_IDS)
                )
            )

            created = updated = 0
            for payload in ORDERS:
                result = await session.execute(
                    select(Order).where(
                        Order.tenant_id == payload["tenant_id"],
                        Order.user_id == payload["user_id"],
                        Order.order_id == payload["order_id"],
                    )
                )
                order = result.scalar_one_or_none()
                if order is None:
                    session.add(Order(**payload))
                    created += 1
                else:
                    for field, value in payload.items():
                        setattr(order, field, value)
                    updated += 1
                print(
                    f"Sample order {'created' if order is None else 'updated'}: "
                    f"tenant_id={payload['tenant_id']} "
                    f"user_id={payload['user_id']} order_id={payload['order_id']} "
                    f"status={payload['status']}"
                )
            await session.commit()
            print(f"Done: {created} created, {updated} updated.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
